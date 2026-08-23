"""Settle which router should decide that a query wants a skill.

Two implementations exist and disagree on the premise.

  live      api.py: skills are retrieved, pooled with prompts, reranked; rank 1
            wins; _coverage_confirms then checks the winner's steps actually
            rank. Treats skill-vs-prompt as a contest for one slot.

  coverage  coverage.best_skill: skills are never retrieved. A skill wins when
            its own steps dominate the prompt ranking. Explicitly refuses the
            score comparison -- "the winning prompt is inside the skill, so the
            two are not competing for the same slot."

The interesting axis is not which finds more skills. It is false positives:
best_skill has no score to lose against, so the risk is serving a stateful
multi-step session to someone who wanted one prompt. coverage.py:69 says the
costs are asymmetric, so that is the number that decides it.

Queries are phrased from the task, not from skill summaries (which would
favour the live router) nor from step titles (which would favour coverage).
NEGATIVE cases are drawn from prompts that are not a step of any skill, so
the correct answer is "no skill".
"""
import asyncio

import pytest

from capillaries.search.api import PromptSearch
from capillaries.skills.coverage import best_skill, score_skills

WORKFLOW = [
    ("we had a production outage overnight and need to run the whole response", "incident-response"),
    ("take me through handling a sev1 from triage to written post-mortem",      "incident-response"),
    ("prepare the full quarterly business review for the board",                "quarterly-business-review"),
    ("pull together last quarter's numbers, variance and the deck",             "quarterly-business-review"),
    ("run the whole negotiation on this vendor agreement",                      "contract-negotiation"),
    ("work through a supplier contract end to end before signing",              "contract-negotiation"),
    ("plan and execute the go-to-market for a new product release",             "product-launch-campaign"),
    ("coordinate positioning, pricing and channels for a launch",               "product-launch-campaign"),
    ("audit our ETL pipeline for schema drift and data quality",                "data-pipeline-audit"),
]

# Correct answer: no skill. Topics covered by standalone prompts only.
SINGLE = [
    "turn this brain dump into a structured document",
    "help me estimate my deep work focus parameters",
    "debrief a sales call and extract the signal",
    "decompose a consulting proposal",
    "write a sub-agent task specification",
    "identify gaps in our content performance",
    "locate the bottleneck in my workflow",
    "build a domain evaluation framework for talent",
]


def _run(coro):
    """Fresh loop per call, same as tests/test_search.py:51.

    get_event_loop() passed standalone and errored inside the full suite,
    where an earlier async test had already closed the shared loop.
    """
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def outcomes():
    """Both routers over the same reranked ranking, so the comparison is
    controlled: only the decision rule differs."""
    search = PromptSearch()
    rows = []
    for query, expected in [(q, e) for q, e in WORKFLOW] + [(q, None) for q in SINGLE]:
        resp = _run(search.search(query, top_k=20))
        live = resp.skill_match.tag if resp.recommendation == "skill" and resp.skill_match else None
        cov = best_skill(resp.results)
        # Why a skill was or wasn't served. Both routers gate on the same
        # coverage evidence, so this is what actually decides the outcome.
        want = {c.tag: c for c in score_skills(resp.results)}.get(expected) if expected else None
        rows.append({"query": query, "expected": expected,
                     "live": live, "coverage": cov.tag if cov else None,
                     "top_is_step": want.top_is_step if want else None,
                     "matched": f"{want.matched}/{want.total}" if want else "<2 steps"})
    return rows


def _rates(rows, key):
    pos = [r for r in rows if r["expected"]]
    neg = [r for r in rows if not r["expected"]]
    hit = sum(1 for r in pos if r[key] == r["expected"])
    wrong = sum(1 for r in pos if r[key] and r[key] != r["expected"])
    fp = sum(1 for r in neg if r[key])
    return hit / len(pos), wrong / len(pos), fp / len(neg)


def test_report(outcomes):
    """Not an assertion — the comparison this file exists to produce."""
    print(f"\n  {'router':10} {'correct':>8} {'wrong-skill':>12} {'false-pos':>10}")
    for key in ("live", "coverage"):
        hit, wrong, fp = _rates(outcomes, key)
        print(f"  {key:10} {hit:>7.0%} {wrong:>12.0%} {fp:>10.0%}")
    print("\n  why workflow queries were declined (both routers gate on this):")
    for r in outcomes:
        if r["expected"] and not r["coverage"]:
            print(f"    {r['query'][:44]:46} steps_in_window={r['matched']:8} top_is_step={r['top_is_step']}")

    print("\n  disagreements:")
    any_diff = False
    for r in outcomes:
        if r["live"] != r["coverage"]:
            any_diff = True
            print(f"    {r['query'][:50]:52} want={r['expected'] or '-':26} "
                  f"live={r['live'] or '-':26} cov={r['coverage'] or '-'}")
    if not any_diff:
        print("    (none — the routers agree on every query)")


def test_neither_router_serves_a_skill_when_none_applies(outcomes):
    """The asymmetric cost. Serving a skill opens a stateful session; being
    wrong here is far more expensive than returning the wrong prompt."""
    for key in ("live", "coverage"):
        _, _, fp = _rates(outcomes, key)
        assert fp == 0.0, (
            f"{key} router served a skill on a single-prompt query: "
            + str([(r['query'], r[key]) for r in outcomes if not r['expected'] and r[key]])
        )


def test_live_router_does_not_regress(outcomes):
    """Pins current behaviour so a future router change is a visible decision."""
    hit, wrong, _ = _rates(outcomes, "live")
    assert wrong == 0.0, "live router served the wrong skill for a workflow query"


def test_coverage_never_serves_less_than_live(outcomes):
    """The settled finding.

    The routers agree almost everywhere, because both gate on the same
    coverage evidence -- REQUIRE_TOP_IS_STEP is the real decision, not the
    router. Where they differ, it is coverage recovering a skill whose steps
    ranked but whose *summary* lost the retrieval, which is exactly the
    failure the fixed SKILL_CANDIDATES budget makes more common as skills are
    added. So coverage must never serve strictly fewer correct skills; if it
    ever does, the scaling argument for switching has died and this test is
    where that shows up.
    """
    live_hit, _, _ = _rates(outcomes, "live")
    cov_hit, _, _ = _rates(outcomes, "coverage")
    assert cov_hit >= live_hit, (
        f"coverage router regressed below live ({cov_hit:.0%} < {live_hit:.0%}); "
        "revisit whether best_skill is still worth keeping"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-s"]))
