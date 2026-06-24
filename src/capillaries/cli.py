"""
Thin CLI for capillaries — one command agents can shell out to.

Usage:
    cap find "build a cash flow model"
    cap find "debug auth middleware" --memory '{"persistent": {"active_domains": ["technical"]}}'
"""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="cap", description="Capillaries prompt retrieval")
    sub = parser.add_subparsers(dest="command")

    find_p = sub.add_parser("find", help="Find best prompt or skill for a situation")
    find_p.add_argument("situation", help="What you need help with")
    find_p.add_argument("--memory", help="MemoryFrame JSON (from arteries)", default=None)
    find_p.add_argument("--prefer", choices=["auto", "single", "skill"], default="auto")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "find":
        from capillaries.find import find_sync, FindResult
        from capillaries.agent.memory_types import MemoryFrame

        memory = None
        if args.memory:
            from capillaries.agent.api import _build_memory_frame
            memory = _build_memory_frame(json.loads(args.memory))

        result = find_sync(args.situation, memory=memory, prefer=args.prefer)
        json.dump(result.to_dict(), sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
