"""DSPy-based prompt optimization pipeline."""

from __future__ import annotations

import hashlib
import uuid

import psycopg2
import psycopg2.extras

from capillaries.config.paths import DB_CONFIG
from capillaries.optimize.capture import ExampleCapture, _resolve_prompt_id
from capillaries.optimize.metrics import get_metric


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


class PromptOptimizer:
    """Optimize prompts using DSPy."""

    def __init__(self, db_config: dict | None = None):
        self._db_config = db_config or DB_CONFIG
        self._capture = ExampleCapture(db_config)

    def optimize(
        self,
        prompt_title: str,
        model: str,
        optimizer: str = "bootstrap_few_shot",
        metric_type: str = "exact_match",
        min_examples: int = 5,
        force: bool = False,
        dry_run: bool = False,
        **metric_kwargs,
    ) -> dict:
        """Run DSPy optimization on a prompt for a given model."""
        import dspy

        prompt_id, prompt_text = self._get_prompt(prompt_title)

        examples = self._load_examples(prompt_id)
        if len(examples) < min_examples:
            raise ValueError(
                f"Need at least {min_examples} golden examples, found {len(examples)}. "
                f"Use 'cap optimize capture' to add more."
            )

        dist = self._capture.source_distribution(prompt_title)
        if not force and dist["external_ratio"] < 0.20:
            raise ValueError(
                f"Only {dist['external_ratio']:.0%} of examples are from external sources "
                f"(need ≥20%). Add external or contrastive examples, or use --force."
            )

        run_id = str(uuid.uuid4())
        if not dry_run:
            self._log_run_start(run_id, prompt_id, model, optimizer,
                                len(examples), metric_type)

        metric_fn = get_metric(metric_type, prompt_title, **metric_kwargs)

        dspy_examples = [
            dspy.Example(
                input_text=ex["input_text"],
                prompt_template=prompt_text,
                output_text=ex["output_text"],
            ).with_inputs("input_text", "prompt_template")
            for ex in examples
        ]

        lm = dspy.LM(model)
        dspy.configure(lm=lm)

        module = PromptExecutor()

        baseline_score = self._evaluate(module, dspy_examples, metric_fn)

        if optimizer == "miprov2":
            tp = dspy.MIPROv2(metric=metric_fn, num_threads=1)
            optimized = tp.compile(module, trainset=dspy_examples)
        else:
            tp = dspy.BootstrapFewShot(metric=metric_fn, max_bootstrapped_demos=4)
            optimized = tp.compile(module, trainset=dspy_examples)

        optimized_score = self._evaluate(optimized, dspy_examples, metric_fn)

        result = {
            "run_id": run_id,
            "prompt_title": prompt_title,
            "prompt_id": prompt_id,
            "model": model,
            "baseline_score": baseline_score,
            "optimized_score": optimized_score,
            "improvement": optimized_score - baseline_score,
        }

        if dry_run:
            result["status"] = "dry_run"
            return result

        if optimized_score <= baseline_score:
            self._log_run_complete(run_id, baseline_score, optimized_score, "no_improvement")
            result["status"] = "no_improvement"
            return result

        optimized_text = self._extract_optimized_text(optimized, prompt_text)

        self._write_variant(prompt_id, model, optimized_text,
                            optimizer, run_id, optimized_score)
        self._update_canonical(prompt_id, optimized_text)
        self._log_run_complete(run_id, baseline_score, optimized_score, "completed")

        result["status"] = "completed"
        result["variant_written"] = True
        return result

    def status(self, prompt_title: str) -> dict:
        """Show optimization history and current variants for a prompt."""
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                prompt_id = _resolve_prompt_id(cur, prompt_title)

                cur.execute("""
                    SELECT model, optimizer, metric_score, created_at
                    FROM prompt_variants
                    WHERE prompt_id = %s AND is_current = TRUE
                    ORDER BY created_at DESC
                """, (prompt_id,))
                variants = [dict(r) for r in cur.fetchall()]

                cur.execute("""
                    SELECT run_id, model, optimizer, metric_type,
                           baseline_score, optimized_score, improvement,
                           status, started_at, completed_at
                    FROM optimization_runs
                    WHERE prompt_id = %s
                    ORDER BY started_at DESC
                    LIMIT 10
                """, (prompt_id,))
                runs = [dict(r) for r in cur.fetchall()]

        dist = self._capture.source_distribution(prompt_title)
        return {
            "prompt_title": prompt_title,
            "variants": variants,
            "recent_runs": runs,
            "example_distribution": dist,
        }

    def compare(self, prompt_title: str) -> dict:
        """Side-by-side comparison of canonical text vs all current variants."""
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                prompt_id = _resolve_prompt_id(cur, prompt_title)

                cur.execute(
                    "SELECT prompt_text FROM prompts WHERE prompt_id = %s",
                    (prompt_id,),
                )
                row = cur.fetchone()
                canonical = row["prompt_text"] if row else ""

                cur.execute("""
                    SELECT model, prompt_text, optimizer, metric_score, created_at
                    FROM prompt_variants
                    WHERE prompt_id = %s AND is_current = TRUE
                    ORDER BY model
                """, (prompt_id,))
                variants = [dict(r) for r in cur.fetchall()]

        return {
            "prompt_title": prompt_title,
            "canonical": canonical,
            "variants": variants,
        }

    def _get_prompt(self, prompt_title: str) -> tuple[str, str]:
        """Return (prompt_id, prompt_text) or raise."""
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT prompt_id, prompt_text FROM prompts WHERE title = %s",
                    (prompt_title,),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"Prompt not found: {prompt_title}")
                return str(row[0]), row[1]

    def _load_examples(self, prompt_id: str) -> list[dict]:
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT input_text, output_text, context_text, source, model
                    FROM golden_examples
                    WHERE prompt_id = %s AND NOT is_negative
                    ORDER BY created_at
                """, (prompt_id,))
                return [dict(r) for r in cur.fetchall()]

    def _evaluate(self, module, examples, metric_fn) -> float:
        scores = []
        for ex in examples:
            try:
                pred = module(input_text=ex.input_text, prompt_template=ex.prompt_template)
                score = metric_fn(pred, ex)
                scores.append(float(score))
            except Exception:
                scores.append(0.0)
        return sum(scores) / max(len(scores), 1)

    def _extract_optimized_text(self, optimized_module, original_text: str) -> str:
        for predictor in optimized_module.predictors():
            if hasattr(predictor, "extended_signature"):
                instructions = predictor.extended_signature.instructions
                if instructions and instructions != original_text:
                    return instructions

            demos = getattr(predictor, "demos", [])
            if demos:
                parts = [original_text, "\n\n## Examples\n"]
                for demo in demos:
                    inp = getattr(demo, "input_text", "")
                    out = getattr(demo, "output_text", "")
                    if inp and out:
                        parts.append(f"\nInput: {inp}\nOutput: {out}\n")
                return "".join(parts)

        return original_text

    def _write_variant(
        self,
        prompt_id: str,
        model: str,
        text: str,
        optimizer: str,
        run_id: str,
        score: float,
    ) -> None:
        content_hash = _content_hash(text)
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE prompt_variants SET is_current = FALSE
                    WHERE prompt_id = %s AND model = %s AND is_current = TRUE
                """, (prompt_id, model))

                cur.execute("""
                    INSERT INTO prompt_variants (
                        variant_id, prompt_id, model, prompt_text,
                        content_hash, optimizer, optimization_run_id, metric_score
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (prompt_id, model, content_hash) DO UPDATE
                    SET is_current = TRUE, metric_score = EXCLUDED.metric_score
                """, (
                    str(uuid.uuid4()), prompt_id, model, text,
                    content_hash, optimizer, run_id, score,
                ))
                conn.commit()

    def _update_canonical(self, prompt_id: str, text: str) -> None:
        content_hash = _content_hash(text)
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE prompts
                    SET prompt_text = %s, content_hash = %s, last_updated = CURRENT_TIMESTAMP
                    WHERE prompt_id = %s
                """, (text, content_hash, prompt_id))
                conn.commit()

    def _log_run_start(self, run_id, prompt_id, model, optimizer,
                       num_examples, metric_type) -> None:
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO optimization_runs (
                        run_id, prompt_id, model, optimizer,
                        num_examples, metric_type
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                """, (run_id, prompt_id, model, optimizer,
                      num_examples, metric_type))
                conn.commit()

    def _log_run_complete(self, run_id, baseline, optimized, status) -> None:
        with psycopg2.connect(**self._db_config) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE optimization_runs
                    SET baseline_score = %s, optimized_score = %s,
                        status = %s, completed_at = CURRENT_TIMESTAMP
                    WHERE run_id = %s
                """, (baseline, optimized, status, run_id))
                conn.commit()


class PromptExecutor:
    """DSPy module wrapping prompt execution."""

    def __init__(self):
        import dspy
        self.generate = dspy.Predict("input_text, prompt_template -> output_text")

    def __call__(self, input_text: str, prompt_template: str):
        return self.generate(input_text=input_text, prompt_template=prompt_template)

    def predictors(self):
        return [self.generate]
