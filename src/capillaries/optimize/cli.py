"""CLI for prompt optimization and golden example management."""

from __future__ import annotations

import argparse
import sys


def cmd_optimize(args: argparse.Namespace) -> None:
    """Run DSPy optimization on a prompt."""
    from capillaries.optimize.dspy_optimize import PromptOptimizer

    optimizer = PromptOptimizer()
    try:
        result = optimizer.optimize(
            prompt_title=args.prompt_title,
            model=args.model,
            optimizer=args.optimizer,
            metric_type=args.metric,
            min_examples=args.min_examples,
            force=args.force,
            dry_run=args.dry_run,
            api_base=args.api_base,
            api_key=args.api_key,
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\nOptimization result for '{args.prompt_title}' ({args.model}):")
    print(f"  Status:          {result['status']}")
    print(f"  Baseline score:  {result['baseline_score']:.3f}")
    print(f"  Optimized score: {result['optimized_score']:.3f}")
    print(f"  Improvement:     {result['improvement']:+.3f}")

    if result.get("variant_written"):
        print(f"  Variant written to DB and canonical text updated.")


def cmd_status(args: argparse.Namespace) -> None:
    """Show optimization status for a prompt."""
    from capillaries.optimize.dspy_optimize import PromptOptimizer

    optimizer = PromptOptimizer()
    info = optimizer.status(args.prompt_title)

    print(f"\nOptimization status: {args.prompt_title}")

    dist = info["example_distribution"]
    print(f"\n  Golden examples: {dist['total']} total")
    print(f"    Memory project: {dist['memory_count']}")
    print(f"    External:       {dist['pure_external_count']}")
    print(f"    Contrastive:    {dist['contrastive_count']}")
    print(f"    Manual:         {dist['manual_count']}")
    print(f"    External ratio: {dist['external_ratio']:.0%}")

    if info["variants"]:
        print(f"\n  Current variants:")
        for v in info["variants"]:
            print(f"    {v['model']}: score={v['metric_score']:.3f}, "
                  f"optimizer={v['optimizer']}, created={v['created_at']}")
    else:
        print(f"\n  No variants yet.")

    if info["recent_runs"]:
        print(f"\n  Recent runs:")
        for r in info["recent_runs"]:
            imp = f"{r['improvement']:+.3f}" if r["improvement"] is not None else "N/A"
            print(f"    {r['started_at']} | {r['model']} | {r['optimizer']} | "
                  f"{r['status']} | improvement: {imp}")


def cmd_compare(args: argparse.Namespace) -> None:
    """Side-by-side comparison of prompt variants."""
    from capillaries.optimize.dspy_optimize import PromptOptimizer

    optimizer = PromptOptimizer()
    info = optimizer.compare(args.prompt_title)

    print(f"\nVariant comparison: {args.prompt_title}")
    print(f"\n{'=' * 60}")
    print(f"CANONICAL (prompts.prompt_text)")
    print(f"{'=' * 60}")
    print(info["canonical"][:500])
    if len(info["canonical"]) > 500:
        print(f"  ... ({len(info['canonical'])} chars total)")

    for v in info["variants"]:
        print(f"\n{'=' * 60}")
        print(f"VARIANT: {v['model']} (optimizer={v['optimizer']}, score={v['metric_score']})")
        print(f"{'=' * 60}")
        print(v["prompt_text"][:500])
        if len(v["prompt_text"]) > 500:
            print(f"  ... ({len(v['prompt_text'])} chars total)")


def cmd_capture(args: argparse.Namespace) -> None:
    """Capture a golden example."""
    from capillaries.optimize.capture import ExampleCapture

    capture = ExampleCapture()

    if args.contrastive:
        if not args.good or not args.bad:
            print("Error: --contrastive requires --good and --bad", file=sys.stderr)
            sys.exit(1)
        good_id, bad_id = capture.capture_contrastive(
            prompt_title=args.prompt_title,
            input_text=args.input,
            good_output=args.good,
            bad_output=args.bad,
            model=args.model_name,
        )
        print(f"Captured contrastive pair: good={good_id}, bad={bad_id}")
    else:
        if not args.output:
            print("Error: --output is required (or use --contrastive)", file=sys.stderr)
            sys.exit(1)

        source = args.source or "manual"
        if source == "external":
            eid = capture.capture_external(
                prompt_title=args.prompt_title,
                input_text=args.input,
                output_text=args.output,
                model=args.model_name,
            )
        elif source == "memory_project":
            eid = capture.capture_from_memory(
                prompt_title=args.prompt_title,
                input_text=args.input,
                output_text=args.output,
                model=args.model_name,
            )
        else:
            eid = capture.capture_manual(
                prompt_title=args.prompt_title,
                input_text=args.input,
                output_text=args.output,
                model=args.model_name,
            )
        print(f"Captured example: {eid} (source={source})")



def cmd_examples(args: argparse.Namespace) -> None:
    """List golden examples for a prompt."""
    from capillaries.optimize.capture import ExampleCapture

    capture = ExampleCapture()
    examples = capture.list_examples(args.prompt_title)
    dist = capture.source_distribution(args.prompt_title)

    print(f"\nGolden examples for '{args.prompt_title}': {dist['total']} total")
    print(f"  External ratio: {dist['external_ratio']:.0%} "
          f"({'OK' if dist['external_ratio'] >= 0.20 else 'BELOW 20% THRESHOLD'})")
    print()

    for ex in examples:
        neg = " [NEGATIVE]" if ex["is_negative"] else ""
        print(f"  {ex['example_id'][:8]}  {ex['source']:15s}  {ex['model'] or 'unknown':20s}  "
              f"{ex['created_at']}{neg}")
        print(f"    Input:  {ex['input_preview']}...")
        print(f"    Output: {ex['output_preview']}...")
        print()


def register_subcommands(
    sub: "argparse._SubParsersAction", run_name: str = "optimize"
) -> dict[str, "Callable[[argparse.Namespace], None]"]:
    """Add the optimize/status/compare/capture/examples parsers onto
    `sub` and return {command_name: handler}. Shared by this module's own
    standalone `main()` and by `cap optimize <...>` (capillaries.cli), so the
    argument definitions live in exactly one place. `run_name` lets the
    caller nest this under a parent group without a stuttering "optimize
    optimize" subcommand — `cap optimize` passes run_name="run".
    """
    opt = sub.add_parser(run_name, help="Run DSPy optimization on a prompt")
    opt.add_argument("prompt_title", help="Title of the prompt to optimize")
    opt.add_argument("--model", required=True, help="Target model (e.g. claude-sonnet-4-6)")
    opt.add_argument("--optimizer", default="bootstrap_few_shot",
                     choices=["bootstrap_few_shot", "miprov2"])
    opt.add_argument("--metric", default="exact_match",
                     choices=["exact_match", "llm_judge", "custom"])
    opt.add_argument("--min-examples", type=int, default=5)
    opt.add_argument("--force", action="store_true",
                     help="Bypass external source ratio check")
    opt.add_argument("--dry-run", action="store_true")
    opt.add_argument("--api-base", default=None,
                     help="OpenAI-compatible endpoint for a local model server "
                          "(e.g. http://127.0.0.1:8001/v1). Omit for a hosted "
                          "provider resolved by name via its env-var API key.")
    opt.add_argument("--api-key", default=None,
                     help="API key for --api-base (default: 'local', most local "
                          "servers don't check it)")

    st = sub.add_parser("status", help="Show optimization history and variants")
    st.add_argument("prompt_title")

    cmp = sub.add_parser("compare", help="Side-by-side diff of variants")
    cmp.add_argument("prompt_title")

    cap = sub.add_parser("capture", help="Capture a golden example")
    cap.add_argument("prompt_title")
    cap.add_argument("--input", required=True, help="Input text / user message")
    cap.add_argument("--output", help="Golden output text")
    cap.add_argument("--source", choices=["manual", "external", "memory_project"],
                     default="manual")
    cap.add_argument("--model-name", help="Model that produced this output")
    cap.add_argument("--contrastive", action="store_true",
                     help="Capture a contrastive pair (requires --good and --bad)")
    cap.add_argument("--good", help="Good output (for contrastive)")
    cap.add_argument("--bad", help="Bad output (for contrastive)")

    ex = sub.add_parser("examples", help="List golden examples")
    ex.add_argument("prompt_title")

    # No `harvest` subcommand: optimize/harvest.py was removed. It captured the
    # retrieved prompt as the golden output, which teaches an optimizer to
    # reproduce the corpus rather than rank it. Golden examples now arrive only
    # through `capture`, until a reward-grounded builder replaces it.
    return {
        run_name: cmd_optimize,
        "status": cmd_status,
        "compare": cmd_compare,
        "capture": cmd_capture,
        "examples": cmd_examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prompt optimization with DSPy"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    commands = register_subcommands(sub, run_name="optimize")

    args = parser.parse_args()
    commands[args.command](args)


if __name__ == "__main__":
    main()
