#!/usr/bin/env python3
"""Generate retrieval summaries for private Obsidian prompts with local Qwen."""

import argparse
import json
import re
from pathlib import Path

import frontmatter
import httpx
import psycopg2

from capillaries.config.paths import DB_CONFIG

LLAMA_URL = "http://127.0.0.1:8001/v1/chat/completions"
LLAMA_MODEL = "qwen3.6-27b"
PLACEHOLDER_RE = re.compile(r"\[[^\]\n]{1,120}\]")

SYSTEM_PROMPT = """You write precise retrieval summaries for AI prompts.
Return only a JSON array of objects with title and summary fields, in the input order.
Each summary must be two sentences and at most 90 words. Sentence one states the
subject plus the intended user, audience, or decision context when clear. Sentence
two states what the model must do and the expected output artifact. Include named
tools, platforms, frameworks, or tech stacks when material. Do not invent facts,
repeat taxonomy labels, or use generic productivity language."""


def placeholders(text: str) -> list[str]:
    return list(dict.fromkeys(PLACEHOLDER_RE.findall(text)))


def build_request(rows: list[dict]) -> str:
    items = []
    for row in rows:
        items.append({
            "title": row["title"],
            "prompt": row["prompt_text"][:5000],
            "required_placeholders": placeholders(row["prompt_text"]),
        })
    return json.dumps(items, ensure_ascii=False)


def parse_response(text: str) -> list[dict]:
    text = text.strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("Qwen did not return a JSON array")
    return json.loads(text[start:end + 1])


def generate(client: httpx.Client, rows: list[dict]) -> dict[str, str]:
    response = client.post(
        LLAMA_URL,
        json={
            "model": LLAMA_MODEL,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_request(rows)},
            ],
        },
    )
    response.raise_for_status()
    results = parse_response(response.json()["choices"][0]["message"]["content"])
    if len(results) != len(rows):
        raise ValueError(f"Expected {len(rows)} summaries, got {len(results)}")

    summaries = {}
    for row, result in zip(rows, results):
        summary = str(result.get("summary", "")).strip()
        if not summary:
            raise ValueError(f"No summary for {row['title']}")
        missing = [token for token in placeholders(row["prompt_text"]) if token not in summary]
        if missing:
            summary = f"{summary.rstrip()} Required context: {', '.join(missing)}."
        summaries[row["title"]] = summary
    return summaries


def write_frontmatter(rows: list[dict], summaries: dict[str, str]) -> int:
    written = 0
    for row in rows:
        path = Path(row["file_path"])
        if not path.exists():
            continue
        post = frontmatter.load(str(path))
        post.metadata["Summary"] = summaries[row["title"]]
        frontmatter.dump(post, str(path))
        written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT title, file_path, prompt_text
                FROM prompts
                WHERE source = 'private' AND COALESCE(summary, '') = ''
                ORDER BY title
            """)
            columns = [column.name for column in cursor.description]
            rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

    if args.limit:
        rows = rows[:args.limit]
    print(f"Generating summaries for {len(rows)} prompts", flush=True)

    completed = 0
    with httpx.Client(timeout=600.0) as client, psycopg2.connect(**DB_CONFIG) as conn:
        for start in range(0, len(rows), args.batch_size):
            batch = rows[start:start + args.batch_size]
            try:
                summaries = generate(client, batch)
            except Exception as exc:
                print(f"Batch failed ({exc}); retrying individually", flush=True)
                summaries = {}
                for row in batch:
                    summaries.update(generate(client, [row]))
            with conn.cursor() as cursor:
                cursor.executemany(
                    """
                    UPDATE prompts
                    SET summary = %s,
                        search_tsv = setweight(to_tsvector('english', %s), 'B') || search_tsv
                    WHERE title = %s
                    """,
                    [
                        (summaries[row["title"]], summaries[row["title"]], row["title"])
                        for row in batch
                    ],
                )
            write_frontmatter(batch, summaries)
            conn.commit()
            completed += len(batch)
            print(f"{completed}/{len(rows)}", flush=True)


if __name__ == "__main__":
    main()
