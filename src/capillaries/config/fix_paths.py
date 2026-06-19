#!/usr/bin/env python3
"""One-shot script to fix remaining file_path mismatches in the DB."""
import psycopg2, re
from pathlib import Path
from capillaries.config.paths import DB_CONFIG

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()
cur.execute("SELECT title, file_path FROM prompts")

fixed = 0
for title, fp in cur.fetchall():
    if Path(fp).exists():
        continue

    d = Path(fp).parent
    stem = Path(fp).stem
    # Strip quotes (straight and curly), parentheses
    cleaned = re.sub(r'[()"\u201c\u201d\u2018\u2019\'"]', '', stem)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    candidate = d / (cleaned + '.md')

    if candidate.exists():
        cur.execute("UPDATE prompts SET file_path = %s WHERE title = %s",
                    (str(candidate), title))
        fixed += 1
        print(f"  FIXED: {title}")
    else:
        print(f"  MISS:  {title}")
        print(f"         tried: {candidate.name}")

conn.commit()
cur.close()
conn.close()
print(f"\nFixed: {fixed}")
