#!/usr/bin/env python3
"""
Pre-download ML models so the first server startup isn't slow.

Usage:
    python scripts/download_models.py                # full profile (~2GB)
    python scripts/download_models.py --profile lite  # embeddings + spaCy (~700MB)
    python scripts/download_models.py --profile external  # nothing (use external API)
"""

import argparse
import subprocess
import sys


MODELS = {
    "full": [
        ("Snowflake/snowflake-arctic-embed-m-v2.0", "encoder", "~500MB"),
        ("mixedbread-ai/mxbai-rerank-base-v2", "crossencoder", "~500MB"),
        ("all-MiniLM-L6-v2", "encoder", "~90MB"),
        ("en_core_web_sm", "spacy", "~12MB"),
    ],
    "lite": [
        ("Snowflake/snowflake-arctic-embed-m-v2.0", "encoder", "~500MB"),
        ("en_core_web_sm", "spacy", "~12MB"),
    ],
    "external": [],
}


def download_encoder(name, size):
    print(f"\n  Downloading {name} ({size})...")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("  ERROR: sentence-transformers not installed.")
        print("  Run: pip install sentence-transformers")
        return False
    SentenceTransformer(name, trust_remote_code=True)
    print(f"  Done: {name}")
    return True


def download_crossencoder(name, size):
    print(f"\n  Downloading {name} ({size})...")
    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        print("  ERROR: sentence-transformers not installed.")
        print("  Run: pip install sentence-transformers")
        return False
    CrossEncoder(name)
    print(f"  Done: {name}")
    return True


def download_spacy(name, size):
    print(f"\n  Downloading spaCy model: {name} ({size})...")
    result = subprocess.run(
        [sys.executable, "-m", "spacy", "download", name],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  ERROR: spaCy download failed. Is spaCy installed?")
        print(f"  Run: pip install spacy")
        if result.stderr:
            print(f"  {result.stderr.strip()}")
        return False
    print(f"  Done: {name}")
    return True


DOWNLOADERS = {
    "encoder": download_encoder,
    "crossencoder": download_crossencoder,
    "spacy": download_spacy,
}


def main():
    parser = argparse.ArgumentParser(description="Pre-download ML models for Capillaries")
    parser.add_argument(
        "--profile",
        choices=["full", "lite", "external"],
        default="full",
        help="Model profile: full (~2GB), lite (~700MB), or external (no local models)",
    )
    args = parser.parse_args()

    if args.profile == "external":
        print("Profile: external — no local models to download.")
        print("Set EMBED_URL in your .env to point to your embedding API.")
        return

    models = MODELS[args.profile]
    print(f"Profile: {args.profile} — downloading {len(models)} model(s)...\n")

    failed = []
    for name, kind, size in models:
        ok = DOWNLOADERS[kind](name, size)
        if not ok:
            failed.append(name)

    print()
    if failed:
        print(f"Failed to download: {', '.join(failed)}")
        print("Install missing packages and re-run this script.")
        sys.exit(1)
    else:
        print("All models downloaded successfully.")


if __name__ == "__main__":
    main()
