#!/usr/bin/env python3
"""
Batch classification implementation for prompts using your custom taxonomies
Integrates with the database setup and uses Anthropic API for classification
"""

import asyncio
import json
import psycopg2
import anthropic
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)

class BatchClassifier:
    """Batch classification of prompts using LLM with your taxonomies"""

    def __init__(self, db_config: Dict[str, str], api_key: str,
                 batch_size: int = 10, max_concurrent: int = 3):
        self.db_config = db_config
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.batch_size = batch_size
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Classification prompt with your exact taxonomies
        self.classification_prompt = """
You are an expert prompt analyst. Analyze this prompt and extract metadata in valid JSON format.

STRICT TAXONOMY REQUIREMENTS:

Intent (select ALL that apply from this exact list):
["adapt", "automate", "build", "communicate", "decide", "explore", "improve", "learn", "prepare", "reflect", "validate"]

Task Type (select ALL that apply from this exact list):
["analyze", "compare", "debug", "evaluate", "model", "optimize", "design", "generate", "synthesize", "explain"]

Domain (select ALL that apply from this exact list, use "personal" for anything not matching):
["AI", "business", "career", "finance", "learning", "personal", "product", "strategy"]

Status (select exactly ONE):
["active", "deferred", "archived"]

Primary Stage (select exactly ONE):
["clarify", "plan", "execute", "verify", "reflect"]

Required Output Format:
{
  "intent": ["learn", "build"],
  "task_type": ["generate", "design"],
  "domain": ["AI", "product"],
  "status": "active",
  "primary_stage": "execute",
  "complexity_level": 3,
  "input_schema": "topic, requirements, constraints",
  "output_schema": "structured plan with deliverables and timeline",
  "context_variables": ["project_scope", "stakeholders", "deadlines"],
  "secondary_stages": ["plan", "verify"],
  "accomplishes": "Creates comprehensive project plans with clear deliverables and timelines",
  "confidence": 0.85
}

IMPORTANT RULES:
1. intent, task_type, and domain are ARRAYS - can have multiple values
2. status and primary_stage are SINGLE values only
3. If domain doesn't fit the 7 categories, use "personal"
4. complexity_level must be integer 1-5 (1=simple, 5=very complex)
5. confidence should be 0.0-1.0 based on how certain you are about the classification
6. All string values must use the exact taxonomy terms listed above

Analyze this prompt:
---
{prompt_text}
---

Return only valid JSON using the exact taxonomy values above:"""

    async def get_pending_prompts(self) -> List[Dict[str, Any]]:
        """Get prompts that need classification from database"""
        conn = psycopg2.connect(**self.db_config)
        cursor = conn.cursor()

        query = """
            SELECT prompt_id, prompt_text, file_path
            FROM prompts
            WHERE backfill_status = 'pending'
            AND (
                array_length(intent, 1) IS NULL
                OR array_length(task_type, 1) IS NULL
                OR array_length(domain, 1) IS NULL
                OR primary_stage IS NULL
            )
            ORDER BY last_updated DESC
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        prompts = []
        for row in rows:
            prompts.append({
                'prompt_id': row[0],
                'prompt_text': row[1],
                'file_path': row[2]
            })

        cursor.close()
        conn.close()

        return prompts

    async def classify_single_prompt(self, prompt_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Classify a single prompt using Anthropic API"""
        async with self.semaphore:
            try:
                # Truncate very long prompts
                prompt_text = prompt_data['prompt_text'][:2000]

                response = await self.client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1000,
                    messages=[{
                        'role': 'user',
                        'content': self.classification_prompt.format(prompt_text=prompt_text)
                    }]
                )

                # Parse JSON response
                response_text = response.content[0].text.strip()

                # Handle potential markdown formatting
                if response_text.startswith('```json'):
                    response_text = response_text[7:]
                if response_text.endswith('```'):
                    response_text = response_text[:-3]

                classification = json.loads(response_text)

                # Add metadata
                classification['prompt_id'] = prompt_data['prompt_id']
                classification['file_path'] = prompt_data['file_path']
                classification['classified_at'] = datetime.utcnow().isoformat()

                # Rate limiting
                await asyncio.sleep(1.0)

                return classification

            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error for {prompt_data['prompt_id']}: {e}")
                logger.debug(f"Raw response: {response_text}")
                return None

            except Exception as e:
                logger.error(f"Classification error for {prompt_data['prompt_id']}: {e}")
                return None

    def validate_classification(self, classification: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate classification against taxonomies"""
        errors = []

        # Required fields
        required_fields = ['intent', 'task_type', 'domain', 'status', 'primary_stage', 'complexity_level']
        for field in required_fields:
            if field not in classification:
                errors.append(f"Missing required field: {field}")

        # Validate taxonomies
        valid_intents = ['adapt', 'automate', 'build', 'communicate', 'decide',
                        'explore', 'improve', 'learn', 'prepare', 'reflect', 'validate']
        if 'intent' in classification:
            if not isinstance(classification['intent'], list):
                errors.append("Intent must be an array")
            else:
                invalid_intents = [i for i in classification['intent'] if i not in valid_intents]
                if invalid_intents:
                    errors.append(f"Invalid intents: {invalid_intents}")

        valid_task_types = ['analyze', 'compare', 'debug', 'evaluate', 'model',
                           'optimize', 'design', 'generate', 'synthesize', 'explain']
        if 'task_type' in classification:
            if not isinstance(classification['task_type'], list):
                errors.append("Task_type must be an array")
            else:
                invalid_types = [t for t in classification['task_type'] if t not in valid_task_types]
                if invalid_types:
                    errors.append(f"Invalid task_types: {invalid_types}")

        valid_domains = ['AI', 'business', 'career', 'finance', 'learning', 'personal', 'product', 'strategy']
        if 'domain' in classification:
            if not isinstance(classification['domain'], list):
                errors.append("Domain must be an array")
            else:
                invalid_domains = [d for d in classification['domain'] if d not in valid_domains]
                if invalid_domains:
                    errors.append(f"Invalid domains: {invalid_domains}")

        valid_statuses = ['active', 'deferred', 'archived']
        if 'status' in classification and classification['status'] not in valid_statuses:
            errors.append(f"Invalid status: {classification['status']}")

        valid_stages = ['clarify', 'plan', 'execute', 'verify', 'reflect']
        if 'primary_stage' in classification and classification['primary_stage'] not in valid_stages:
            errors.append(f"Invalid primary_stage: {classification['primary_stage']}")

        # Complexity level validation
        if 'complexity_level' in classification:
            complexity = classification['complexity_level']
            if not isinstance(complexity, int) or complexity < 1 or complexity > 5:
                errors.append(f"Invalid complexity_level: {complexity} (must be 1-5)")

        return len(errors) == 0, errors

    async def save_classification_to_db(self, classification: Dict[str, Any]) -> bool:
        """Save classification results to database"""
        try:
            conn = psycopg2.connect(**self.db_config)
            cursor = conn.cursor()

            update_sql = """
                UPDATE prompts SET
                    intent = %s,
                    task_type = %s,
                    domain = %s,
                    status = %s,
                    primary_stage = %s,
                    secondary_stages = %s,
                    complexity_level = %s,
                    input_schema = %s,
                    output_schema = %s,
                    context_variables = %s,
                    accomplishes = %s,
                    metadata_confidence = jsonb_build_object(
                        'classification_confidence', %s,
                        'classified_at', %s,
                        'classification_version', 'v1'
                    ),
                    last_classified = CURRENT_TIMESTAMP,
                    backfill_status = 'completed'
                WHERE prompt_id = %s
            """

            cursor.execute(update_sql, (
                classification.get('intent', []),
                classification.get('task_type', []),
                classification.get('domain', []),
                classification.get('status', 'active'),
                classification.get('primary_stage'),
                classification.get('secondary_stages', []),
                classification.get('complexity_level'),
                classification.get('input_schema'),
                classification.get('output_schema'),
                classification.get('context_variables', []),
                classification.get('accomplishes'),
                classification.get('confidence', 0.5),
                classification.get('classified_at'),
                classification['prompt_id']
            ))

            conn.commit()
            cursor.close()
            conn.close()

            return True

        except Exception as e:
            logger.error(f"Database save error for {classification['prompt_id']}: {e}")
            return False

    async def process_batch(self, prompts_batch: List[Dict[str, Any]]) -> Dict[str, int]:
        """Process a batch of prompts"""
        logger.info(f"Processing batch of {len(prompts_batch)} prompts...")

        # Classify prompts in parallel
        tasks = [self.classify_single_prompt(prompt) for prompt in prompts_batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        batch_stats = {
            'successful': 0,
            'failed': 0,
            'validation_errors': 0
        }

        for i, result in enumerate(results):
            prompt_id = prompts_batch[i]['prompt_id']

            if isinstance(result, Exception):
                logger.error(f"Exception for {prompt_id}: {result}")
                batch_stats['failed'] += 1
                continue

            if result is None:
                logger.error(f"No result for {prompt_id}")
                batch_stats['failed'] += 1
                continue

            # Validate classification
            is_valid, errors = self.validate_classification(result)
            if not is_valid:
                logger.error(f"Validation errors for {prompt_id}: {errors}")
                batch_stats['validation_errors'] += 1
                continue

            # Save to database
            saved = await self.save_classification_to_db(result)
            if saved:
                logger.info(f"✅ Classified {prompt_id}: {result.get('intent', [])} | "
                           f"{result.get('task_type', [])} | {result.get('domain', [])} | "
                           f"confidence: {result.get('confidence', 0):.2f}")
                batch_stats['successful'] += 1
            else:
                logger.error(f"❌ Failed to save {prompt_id}")
                batch_stats['failed'] += 1

        return batch_stats

    async def process_all_prompts(self) -> Dict[str, int]:
        """Process all pending prompts in batches"""
        prompts_to_classify = await self.get_pending_prompts()

        if not prompts_to_classify:
            logger.info("No prompts need classification")
            return {'total': 0, 'successful': 0, 'failed': 0, 'validation_errors': 0}

        logger.info(f"Starting classification of {len(prompts_to_classify)} prompts")

        total_stats = {
            'total': len(prompts_to_classify),
            'successful': 0,
            'failed': 0,
            'validation_errors': 0
        }

        # Process in batches
        for i in range(0, len(prompts_to_classify), self.batch_size):
            batch = prompts_to_classify[i:i + self.batch_size]
            batch_num = i // self.batch_size + 1
            total_batches = (len(prompts_to_classify) - 1) // self.batch_size + 1

            logger.info(f"Processing batch {batch_num}/{total_batches}")

            batch_stats = await self.process_batch(batch)

            # Update totals
            for key in ['successful', 'failed', 'validation_errors']:
                total_stats[key] += batch_stats[key]

            logger.info(f"Batch {batch_num} complete: "
                       f"{batch_stats['successful']}/{len(batch)} successful")

            # Brief pause between batches
            if i + self.batch_size < len(prompts_to_classify):
                await asyncio.sleep(2.0)

        # Final summary
        success_rate = total_stats['successful'] / total_stats['total'] * 100
        logger.info(f"\nClassification complete:")
        logger.info(f"  Total processed: {total_stats['total']}")
        logger.info(f"  Successful: {total_stats['successful']} ({success_rate:.1f}%)")
        logger.info(f"  Failed: {total_stats['failed']}")
        logger.info(f"  Validation errors: {total_stats['validation_errors']}")

        return total_stats

# Standalone script for batch classification
async def main():
    """Run batch classification standalone"""
    import os

    DB_CONFIG = {
        'host': 'localhost',
        'database': 'prompt_flow',
        'user': 'bao',
        'password': ''
    }

    # Get API key
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        print("Please set ANTHROPIC_API_KEY environment variable")
        return

    # Create classifier
    classifier = BatchClassifier(
        db_config=DB_CONFIG,
        api_key=api_key,
        batch_size=10,
        max_concurrent=3
    )

    # Run classification
    results = await classifier.process_all_prompts()

    print(f"\nClassification Results:")
    print(f"Total: {results['total']}")
    print(f"Successful: {results['successful']}")
    print(f"Failed: {results['failed']}")
    print(f"Validation Errors: {results['validation_errors']}")

if __name__ == "__main__":
    asyncio.run(main())