#!/usr/bin/env python3
"""
Batch classification of prompts using Anthropic API.
Sends 10-15 prompts per API call for cost efficiency.
Model: claude-haiku-4-5-20251001
"""

import asyncio
import json
import psycopg2
import anthropic
import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)

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

CONFIDENCE_THRESHOLD = 0.75

# ---------------------------------------------------------------------------
# Prompt templates
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
    def __init__(self, db_config: Dict[str, str], api_key: str,
                 batch_size: int = 12, max_concurrent: int = 3):
        self.db_config = db_config
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.batch_size = batch_size
        self.semaphore = asyncio.Semaphore(max_concurrent)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_prompt_blocks(self, prompts: List[Dict[str, Any]]) -> str:
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

    # ------------------------------------------------------------------
    # API call — batch of 10-15 prompts in a single request
    # ------------------------------------------------------------------

    async def classify_batch(
        self, prompts: List[Dict[str, Any]]
    ) -> List[Optional[Dict[str, Any]]]:
        async with self.semaphore:
            try:
                user_content = USER_PROMPT_TEMPLATE.format(
                    prompt_blocks=self._build_prompt_blocks(prompts),
                    n=len(prompts)
                )

                response = await self.client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    messages=[{'role': 'user', 'content': user_content}]
                )

                text = response.content[0].text.strip()
                # Strip accidental markdown fences
                if text.startswith('```'):
                    text = text.split('\n', 1)[1]
                if text.endswith('```'):
                    text = text.rsplit('```', 1)[0].strip()

                results = json.loads(text)

                if not isinstance(results, list) or len(results) != len(prompts):
                    logger.error(
                        f"Expected {len(prompts)} results, got "
                        f"{len(results) if isinstance(results, list) else type(results).__name__}"
                    )
                    return [None] * len(prompts)

                for i, result in enumerate(results):
                    result['prompt_id'] = prompts[i]['prompt_id']

                return results

            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error in batch: {e}")
                return [None] * len(prompts)
            except Exception as e:
                logger.error(f"Batch classification error: {e}")
                return [None] * len(prompts)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_classification(
        self, classification: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        errors = []

        required = [
            'intent', 'task_type', 'domain', 'primary_stage', 'complexity',
            'accepts_prior_output', 'has_template_vars', 'is_chain_prompt', 'confidence'
        ]
        for field in required:
            if field not in classification:
                errors.append(f"Missing field: {field}")

        # Array + enum fields
        for field in ('intent', 'task_type', 'domain'):
            if field in classification:
                if not isinstance(classification[field], list):
                    errors.append(f"{field} must be an array")
                else:
                    invalid = [v for v in classification[field] if v not in VALID_VALUES[field]]
                    if invalid:
                        errors.append(f"Invalid {field} values: {invalid}")

        if 'primary_stage' in classification:
            if classification['primary_stage'] not in VALID_VALUES['primary_stage']:
                errors.append(f"Invalid primary_stage: {classification['primary_stage']}")

        if 'complexity' in classification:
            c = classification['complexity']
            if not isinstance(c, int) or not (1 <= c <= 5):
                errors.append(f"complexity must be integer 1–5, got: {c}")

        for bool_field in ('accepts_prior_output', 'has_template_vars', 'is_chain_prompt'):
            if bool_field in classification:
                if not isinstance(classification[bool_field], bool):
                    errors.append(f"{bool_field} must be boolean")

        if 'confidence' in classification:
            if not isinstance(classification['confidence'], dict):
                errors.append("confidence must be a per-field dict")

        return len(errors) == 0, errors

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    async def get_pending_prompts(self) -> List[Dict[str, Any]]:
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT prompt_id, prompt_text, file_path
            FROM prompts
            WHERE backfill_status = 'pending'
            ORDER BY last_updated DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        return [
            {
                'prompt_id': r[0],
                'prompt_text': r[1],
                'title': r[2].rsplit('/', 1)[-1].replace('.md', '') if r[2] else r[0]
            }
            for r in rows
        ]

    async def save_classification(self, classification: Dict[str, Any]) -> bool:
        try:
            confidence = classification.get('confidence', {})
            status = self._backfill_status(confidence)

            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()
            cursor.execute("""
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
                classification.get('intent', []),
                classification.get('task_type', []),
                classification.get('domain', []),
                classification.get('primary_stage'),
                classification.get('complexity'),
                classification.get('accepts_prior_output', False),
                classification.get('has_template_vars', False),
                classification.get('is_chain_prompt', False),
                json.dumps(confidence),
                'v1.0-haiku',
                status,
                classification['prompt_id']
            ))
            conn.commit()
            cursor.close()
            conn.close()
            return True

        except Exception as e:
            logger.error(f"DB save error for {classification['prompt_id']}: {e}")
            return False

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def process_all_prompts(self) -> Dict[str, int]:
        pending = await self.get_pending_prompts()
        if not pending:
            logger.info("No prompts pending classification")
            return {'total': 0, 'successful': 0, 'failed': 0, 'needs_review': 0}

        logger.info(f"Classifying {len(pending)} prompts in batches of {self.batch_size}")
        stats = {'total': len(pending), 'successful': 0, 'failed': 0, 'needs_review': 0}

        total_batches = (len(pending) - 1) // self.batch_size + 1

        for i in range(0, len(pending), self.batch_size):
            batch = pending[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            logger.info(f"Batch {batch_num}/{total_batches} ({len(batch)} prompts)")

            results = await self.classify_batch(batch)

            for j, result in enumerate(results):
                prompt_id = batch[j]['prompt_id']

                if result is None:
                    stats['failed'] += 1
                    continue

                is_valid, errors = self.validate_classification(result)
                if not is_valid:
                    logger.error(f"Validation failed for {prompt_id}: {errors}")
                    stats['failed'] += 1
                    continue

                saved = await self.save_classification(result)
                if saved:
                    confidence = result.get('confidence', {})
                    bstatus = self._backfill_status(confidence)
                    if bstatus == 'needs_review':
                        stats['needs_review'] += 1
                    stats['successful'] += 1
                    logger.info(
                        f"✓ {prompt_id} [{bstatus}] "
                        f"intent={result.get('intent')} "
                        f"stage={result.get('primary_stage')} "
                        f"chain={result.get('is_chain_prompt')}"
                    )
                else:
                    stats['failed'] += 1

            if i + self.batch_size < len(pending):
                await asyncio.sleep(1.0)

        logger.info(
            f"\nDone — {stats['successful']}/{stats['total']} classified "
            f"({stats['needs_review']} need review, {stats['failed']} failed)"
        )
        return stats


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    import os

    DB_CONFIG = {
        'host': 'localhost',
        'database': 'prompt_flow',
        'user': 'bao',
        'password': ''
    }

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("Set ANTHROPIC_API_KEY environment variable")
        return

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    classifier = BatchClassifier(db_config=DB_CONFIG, api_key=api_key)
    results = await classifier.process_all_prompts()

    print(f"\nResults:")
    for k, v in results.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    asyncio.run(main())
