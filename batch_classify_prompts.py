#!/usr/bin/env python3
"""
Batch classification of prompts using a local Ollama model.
Sends prompts in batches; writes results back to PostgreSQL.
"""

import asyncio
import json
import logging
import httpx
import psycopg2
from typing import List, Dict, Any, Optional, Tuple
from path_config import DB_CONFIG

logger = logging.getLogger(__name__)

OLLAMA_URL  = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen3.5:latest"
BATCH_SIZE  = 1   # one at a time for reliability with local model
MAX_RETRIES = 2
CONFIDENCE_THRESHOLD = 0.75

# ---------------------------------------------------------------------------
# Taxonomy
# ---------------------------------------------------------------------------

VALID_VALUES: Dict[str, set] = {
    'intent': {
        'adapt', 'automate', 'build', 'communicate', 'decide', 'explore',
        'improve', 'learn', 'prepare', 'reflect', 'validate'
    },
    'task_type': {
        'analyze', 'compare', 'debug', 'evaluate', 'model', 'optimize',
        'design', 'generate', 'synthesize', 'explain'
    },
    'domain': {
        'AI', 'business', 'career', 'finance', 'learning', 'personal',
        'product', 'strategy', 'writing', 'technical'
    },
    'primary_stage': {'clarify', 'plan', 'execute', 'verify', 'reflect'},
}

# ---------------------------------------------------------------------------
# Prompt templates (unchanged from original)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a prompt metadata classifier. Analyze each prompt and \
classify its characteristics using ONLY the allowed values for each field.

Return a valid JSON array only. No explanation, no markdown fences, no commentary.
Each object in the array must correspond to one prompt, in the same order given.

RULES:
- intent and task_type: arrays of 1–3 values each
- domain: array of 1–2 values
- primary_stage, complexity, accepts_prior_output, has_template_vars, is_chain_prompt: single values
- confidence: per-field dict with scores 0.0–1.0 reflecting how clearly the prompt signals each field
- If a field is ambiguous, pick the closest match and lower its confidence score"""

USER_PROMPT_TEMPLATE = """\
ALLOWED VALUES:
intent:        adapt | automate | build | communicate | decide | explore | improve | learn | prepare | reflect | validate
task_type:     analyze | compare | debug | evaluate | model | optimize | design | generate | synthesize | explain
domain:        AI | business | career | finance | learning | personal | product | strategy | writing | technical
primary_stage: clarify | plan | execute | verify | reflect
complexity:    1 | 2 | 3 | 4 | 5

COMPLEXITY SCALE:
1 = Single instruction, no role, minimal structure
2 = Defined role + clear output format, low context requirement
3 = Expert role + multi-point output + moderate context required
4 = Expert role + multi-phase output + substantial input data required
5 = Multi-phase workflow or embedded step chains, comprehensive artifact output

accepts_prior_output: true if the prompt explicitly or implicitly expects a previous LLM output as its main input
  (signals: "[PASTE PRIOR OUTPUT]", "You previously wrote", "Given the above", "Based on your analysis",
   "Now attack your previous answer", "your previous answer", "prior response")

has_template_vars: true if the prompt contains user-fillable ALL-CAPS bracket placeholders
  (signals: [COMPANY], [YOUR X], [LIST], [NUMBER], [DESCRIBE], [ENTER], [AMOUNT], [PRODUCT]
   NOT: structural/example brackets like [1], [see above], [optional])

is_chain_prompt: true if the prompt internally embeds multiple numbered steps or phases to be run sequentially
  (signals: "Step 1", "Step 2", "Phase 1", "Phase 2", "Prompt Chain:", explicit multi-step structure)

---

EXAMPLES:

Prompt title: "Adversarial Stress Test Template"
Prompt text: "[YOUR INITIAL REQUEST AND MODEL RESPONSE]\\n\\nNow attack your previous answer:\\n1. Identify five specific ways it could be wrong..."
Output:
{
  "intent": ["improve", "validate"],
  "task_type": ["evaluate", "analyze"],
  "domain": ["AI"],
  "primary_stage": "verify",
  "complexity": 2,
  "accepts_prior_output": true,
  "has_template_vars": true,
  "is_chain_prompt": false,
  "confidence": {"intent": 0.92, "task_type": 0.95, "domain": 0.70, "primary_stage": 0.90, "complexity": 0.88}
}

Prompt title: "Management Consultant - Executive Summary"
Prompt text: "I'm a strategy consultant writing an executive summary for a detailed analysis. Audience is C-suite.\\n\\nAnalysis Scope: [What question you were answering]\\n..."
Output:
{
  "intent": ["communicate", "build"],
  "task_type": ["synthesize", "generate"],
  "domain": ["business", "strategy"],
  "primary_stage": "execute",
  "complexity": 3,
  "accepts_prior_output": false,
  "has_template_vars": true,
  "is_chain_prompt": false,
  "confidence": {"intent": 0.90, "task_type": 0.88, "domain": 0.95, "primary_stage": 0.85, "complexity": 0.85}
}

Prompt title: "Department Budget vs. Actual Tracker"
Prompt text: "Prompt Chain:\\n\\nStep 1 - Setup Structure:\\nCreate a department budget tracker with this structure..."
Output:
{
  "intent": ["build", "model"],
  "task_type": ["design", "generate"],
  "domain": ["finance", "business"],
  "primary_stage": "execute",
  "complexity": 5,
  "accepts_prior_output": false,
  "has_template_vars": false,
  "is_chain_prompt": true,
  "confidence": {"intent": 0.88, "task_type": 0.90, "domain": 0.95, "primary_stage": 0.85, "complexity": 0.92}
}

---

NOW CLASSIFY THE FOLLOWING PROMPTS:

{prompt_blocks}

Return a JSON array of {n} objects in the same order as the prompts above."""


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

class BatchClassifier:
    def __init__(self, db_config: Dict, batch_size: int = BATCH_SIZE):
        self.db_config = db_config
        self.batch_size = batch_size

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_prompt_blocks(self, prompts: List[Dict]) -> str:
        blocks = []
        for i, p in enumerate(prompts, 1):
            title = p.get('title', p['prompt_id'])
            text = p['prompt_text'][:2000]
            blocks.append(f"PROMPT {i}\nTitle: {title}\n---\n{text}")
        return "\n\n".join(blocks)

    def _backfill_status(self, confidence: Dict[str, float]) -> str:
        if not confidence:
            return 'needs_review'
        return 'complete' if min(confidence.values()) >= CONFIDENCE_THRESHOLD else 'needs_review'

    def _repair_classification(self, c: Dict) -> Dict:
        """Fix common cross-field confusion: task_type values in intent and vice versa."""
        intent_only   = VALID_VALUES['intent']
        tasktype_only = VALID_VALUES['task_type']

        if 'intent' in c and isinstance(c['intent'], list):
            misplaced = [v for v in c['intent'] if v not in intent_only and v in tasktype_only]
            if misplaced:
                c['intent'] = [v for v in c['intent'] if v in intent_only]
                existing_tt = c.get('task_type', [])
                c['task_type'] = list(dict.fromkeys(existing_tt + misplaced))  # dedupe, preserve order

        if 'task_type' in c and isinstance(c['task_type'], list):
            misplaced = [v for v in c['task_type'] if v not in tasktype_only and v in intent_only]
            if misplaced:
                c['task_type'] = [v for v in c['task_type'] if v in tasktype_only]
                existing_i = c.get('intent', [])
                c['intent'] = list(dict.fromkeys(existing_i + misplaced))

        # Drop any remaining invalid values rather than hard-failing the whole record
        for field in ('intent', 'task_type', 'domain'):
            if field in c and isinstance(c[field], list):
                c[field] = [v for v in c[field] if v in VALID_VALUES[field]]

        if 'primary_stage' in c and c['primary_stage'] not in VALID_VALUES['primary_stage']:
            c['primary_stage'] = None  # will fail validation cleanly

        return c

    def _extract_json(self, text: str) -> str:
        """Strip markdown fences and extract the JSON array."""
        text = text.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1]
        if text.endswith('```'):
            text = text.rsplit('```', 1)[0].strip()
        # Find first '[' in case model added preamble despite instructions
        start = text.find('[')
        if start != -1:
            text = text[start:]
        return text

    # ------------------------------------------------------------------
    # Ollama API call
    # ------------------------------------------------------------------

    async def classify_batch(self, prompts: List[Dict]) -> List[Optional[Dict]]:
        user_content = (
            USER_PROMPT_TEMPLATE
            .replace("{prompt_blocks}", self._build_prompt_blocks(prompts))
            .replace("{n}", str(len(prompts)))
        )
        payload = {
            "model": OLLAMA_MODEL,
            "stream": False,
            "options": {"temperature": 0.1},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ]
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=600.0) as client:
                    response = await client.post(OLLAMA_URL, json=payload)
                    response.raise_for_status()

                text = response.json()["message"]["content"]
                text = self._extract_json(text)
                results = json.loads(text)

                if not isinstance(results, list) or len(results) != len(prompts):
                    raise ValueError(
                        f"Expected {len(prompts)} results, got "
                        f"{len(results) if isinstance(results, list) else type(results)}"
                    )

                for i, result in enumerate(results):
                    result['prompt_id'] = prompts[i]['prompt_id']

                return results

            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Attempt {attempt}/{MAX_RETRIES} — parse error: {e}")
                if attempt == MAX_RETRIES:
                    return [None] * len(prompts)
                await asyncio.sleep(2.0)

            except Exception as e:
                logger.error(f"Attempt {attempt}/{MAX_RETRIES} — request error: {e}")
                if attempt == MAX_RETRIES:
                    return [None] * len(prompts)
                await asyncio.sleep(2.0)

        return [None] * len(prompts)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_classification(self, c: Dict) -> Tuple[bool, List[str]]:
        errors = []
        required = [
            'intent', 'task_type', 'domain', 'primary_stage', 'complexity',
            'accepts_prior_output', 'has_template_vars', 'is_chain_prompt', 'confidence'
        ]
        for field in required:
            if field not in c:
                errors.append(f"Missing field: {field}")

        for field in ('intent', 'task_type', 'domain'):
            if field in c:
                if not isinstance(c[field], list):
                    errors.append(f"{field} must be an array")
                else:
                    invalid = [v for v in c[field] if v not in VALID_VALUES[field]]
                    if invalid:
                        errors.append(f"Invalid {field} values: {invalid}")

        if 'primary_stage' in c and c['primary_stage'] not in VALID_VALUES['primary_stage']:
            errors.append(f"Invalid primary_stage: {c['primary_stage']}")

        if 'complexity' in c:
            if not isinstance(c['complexity'], int) or not (1 <= c['complexity'] <= 5):
                errors.append(f"complexity must be integer 1–5, got: {c['complexity']}")

        for bf in ('accepts_prior_output', 'has_template_vars', 'is_chain_prompt'):
            if bf in c and not isinstance(c[bf], bool):
                errors.append(f"{bf} must be boolean")

        if 'confidence' in c and not isinstance(c['confidence'], dict):
            errors.append("confidence must be a per-field dict")

        return len(errors) == 0, errors

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def get_pending_prompts(self) -> List[Dict]:
        conn = psycopg2.connect(**self.db_config)
        cur = conn.cursor()
        cur.execute("""
            SELECT prompt_id, prompt_text, file_path
            FROM prompts
            WHERE backfill_status = 'pending'
            ORDER BY last_updated DESC
        """)
        rows = cur.fetchall()
        cur.close(); conn.close()
        return [
            {
                'prompt_id': r[0],
                'prompt_text': r[1],
                'title': r[2].rsplit('/', 1)[-1].replace('.md', '') if r[2] else r[0]
            }
            for r in rows
        ]

    def save_classification(self, c: Dict) -> bool:
        try:
            confidence = c.get('confidence', {})
            status = self._backfill_status(confidence)
            conn = psycopg2.connect(**self.db_config)
            cur = conn.cursor()
            cur.execute("""
                UPDATE prompts SET
                    intent                = %s,
                    task_type             = %s,
                    domain                = %s,
                    primary_stage         = %s,
                    complexity_level      = %s,
                    accepts_prior_output  = %s,
                    has_template_vars     = %s,
                    is_chain_prompt       = %s,
                    metadata_confidence   = %s,
                    classification_version = %s,
                    last_classified       = CURRENT_TIMESTAMP,
                    backfill_status       = %s
                WHERE prompt_id = %s
            """, (
                c.get('intent', []),
                c.get('task_type', []),
                c.get('domain', []),
                c.get('primary_stage'),
                c.get('complexity'),
                c.get('accepts_prior_output', False),
                c.get('has_template_vars', False),
                c.get('is_chain_prompt', False),
                json.dumps(confidence),
                f'v1.0-{OLLAMA_MODEL.replace(":", "-")}',
                status,
                c['prompt_id']
            ))
            conn.commit()
            cur.close(); conn.close()
            return True
        except Exception as e:
            logger.error(f"DB save error for {c['prompt_id']}: {e}")
            return False

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def process_all_prompts(self) -> Dict[str, int]:
        pending = self.get_pending_prompts()
        if not pending:
            logger.info("No prompts pending classification")
            return {'total': 0, 'successful': 0, 'failed': 0, 'needs_review': 0}

        total_batches = (len(pending) - 1) // self.batch_size + 1
        logger.info(f"Classifying {len(pending)} prompts — {total_batches} batches of {self.batch_size}")
        stats = {'total': len(pending), 'successful': 0, 'failed': 0, 'needs_review': 0}

        for i in range(0, len(pending), self.batch_size):
            batch = pending[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            logger.info(f"Batch {batch_num}/{total_batches} ({len(batch)} prompts) ...")

            results = await self.classify_batch(batch)

            for j, result in enumerate(results):
                prompt_id = batch[j]['prompt_id']
                if result is None:
                    stats['failed'] += 1
                    continue

                result = self._repair_classification(result)
                is_valid, errors = self.validate_classification(result)
                if not is_valid:
                    logger.warning(f"  ✗ {prompt_id} — validation errors: {errors}")
                    stats['failed'] += 1
                    continue

                if self.save_classification(result):
                    bstatus = self._backfill_status(result.get('confidence', {}))
                    if bstatus == 'needs_review':
                        stats['needs_review'] += 1
                    stats['successful'] += 1
                    logger.info(
                        f"  ✓ {prompt_id} [{bstatus}] "
                        f"intent={result.get('intent')} "
                        f"stage={result.get('primary_stage')} "
                        f"complexity={result.get('complexity')}"
                    )
                else:
                    stats['failed'] += 1

        logger.info(
            f"\nDone — {stats['successful']}/{stats['total']} classified "
            f"({stats['needs_review']} need review, {stats['failed']} failed)"
        )
        return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(message)s',
        handlers=[
            logging.FileHandler('classification.log'),
            logging.StreamHandler()
        ]
    )
    classifier = BatchClassifier(db_config=DB_CONFIG)
    stats = await classifier.process_all_prompts()
    print(f"\nFinal results: {stats}")

    # Auto-sync classified prompts back to Obsidian frontmatter
    if stats['successful'] > 0:
        print("\nSyncing classifications to Obsidian frontmatter...")
        from sync_to_obsidian import get_classified_prompts, sync_prompt_to_file, mark_synced
        prompts = get_classified_prompts()
        synced = []
        for p in prompts:
            if sync_prompt_to_file(p):
                synced.append(p['prompt_id'])
        if synced:
            mark_synced(synced)
        print(f"Synced {len(synced)} files to Obsidian")


if __name__ == "__main__":
    asyncio.run(main())
