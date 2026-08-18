"""
Thin CLI for capillaries — one command agents can shell out to.

Usage:
    cap find "build a cash flow model"
    cap find "debug auth middleware" --context '{"persistent": {"active_domains": ["technical"]}}'
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
    find_p.add_argument("--context", help="MemoryFrame JSON (from arteries)", default=None)
    find_p.add_argument("--prefer", choices=["auto", "single", "skill"], default="auto")

    from capillaries.optimize.cli import register_subcommands
    opt_p = sub.add_parser("optimize", help="DSPy prompt/skill optimization (run/status/compare/capture/examples)")
    opt_sub = opt_p.add_subparsers(dest="optimize_command", required=True)
    optimize_commands = register_subcommands(opt_sub, run_name="run")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "optimize":
        optimize_commands[args.optimize_command](args)
        return

    if args.command == "find":
        from capillaries.find import find_sync, FindResult

        context = None
        if args.context:
            from capillaries.agent.api import _build_context_frame
            context = _build_context_frame(json.loads(args.context))

        result = find_sync(args.situation, context=context, prefer=args.prefer)
        json.dump(result.to_dict(), sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
