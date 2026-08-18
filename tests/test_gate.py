"""Retrieval-gate tests.

The gate decides *whether* to retrieve, on two signals: a semantic match to the
corpus AND a complexity band (not too simple, not too complicated). Type is not
consulted. See capillaries/agent/gate.py.

Most of this suite is hermetic — `_band_decision` and the Stage-1 heuristics are
pure functions, so they need no Postgres and no embedding endpoint, unlike
test_search.py. Only the handful of `@pytest.mark.db` cases hit live services,
to confirm the frozen similarities below still reflect the real corpus.

Run hermetic only:  pytest tests/test_gate.py -m "not db"
Run everything:     pytest tests/test_gate.py
"""
import asyncio

import pytest

from capillaries.agent.gate import (
    SIMILARITY_THRESHOLD,
    SPECIFICITY_THRESHOLD,
    WORD_BAND_HIGH,
    WORD_BAND_LOW,
    GateDecision,
    _band_decision,
    _heuristic_check,
    gate,
    specification_density,
)


def run(coro):
    """Run a coroutine synchronously — a fresh loop per call, so no dependence
    on a pre-existing event loop (get_event_loop() is deprecated in 3.12)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Labelled real messages: (label, text, frozen_sim, want_retrieve)
#
# frozen_sim is the measured nearest-neighbour similarity against the reembedded
# corpus, so the decision layer can be tested without an embedding call. The db
# test below re-measures a few of these and fails if the corpus has drifted far
# enough to invalidate the calibration.
# ---------------------------------------------------------------------------
# The real planner prompt as plexus sends it — PLAN_PROMPT + goal + context + the
# JSON output schema. It is 122 words at density ~0.10, which overlaps the feature
# specs completely: word count and density cannot separate planner from feature,
# because BOTH are fully-specified instructions. Under the "retrieve only for
# vague/open queries" rule this is the correct outcome — the planner is a spec
# input and skips, exactly like a feature. A plexus run therefore retrieves
# nothing; retrieval is reserved for genuinely open interactive queries.
PLANNER = (
    "You are planning a software goal that will be built one feature at a time by a\n"
    "coding agent, each feature verified before the next starts.\n\n"
    "Goal: Add textkit.wordwrap(s, width) that wraps text to the given column width "
    'without breaking words. wordwrap("the quick brown fox", 10) == "the quick\nbrown fox".\n\n'
    "Context: Python 3.12, stdlib only. Package dir textkit/, tests in tests/.\n\n"
    "Definition of done — this must pass when all features are built: python3 -m pytest -q\n\n"
    'Reply with ONLY a JSON array of features, in build order. Each feature:\n'
    '{"id": "<short-slug>", "title": "<one line>",\n'
    '  "spec": "<what to implement, self-contained>",\n'
    '  "acceptance": "<shell command that exits 0 iff this feature works>"}\n'
    "Keep each feature small enough to land in one agent session."
)
SPEC_0 = (
    "Create textkit/__init__.py exporting slugify(s). Behavior: NFKD-normalize and "
    "drop combining marks, encode ASCII ignoring errors, lowercase, replace each run "
    "of non-alphanumeric chars with a single hyphen, strip leading/trailing hyphens. "
    "slugify('  Héllo, World!  ') == 'hello-world'. Add tests/test_slugify.py covering "
    "accents, punctuation runs, and edge cases including the empty string."
)
SPEC_1 = (
    "Add truncate(s, n, suffix='...') to textkit/__init__.py and export it alongside "
    "slugify. If len(s) <= n return s unchanged; otherwise return at most n characters "
    "total including the suffix, breaking on a word boundary when one exists in the kept "
    "region. truncate('hello world', 8) == 'hello...'. Add tests/test_truncate.py."
)
TERSE_SPEC = (
    "Add slugify(s) to textkit/__init__.py; slugify('Hello')=='hello'; "
    "tests in tests/test_slugify.py"
)
TRACEBACK = (
    "OPENAI_API_KEY=x uvicorn agent.app:app --port 8080 Traceback most recent call last "
    "File app.py line 12 ModuleNotFoundError No module named agent.graph"
)

#         label              text                         frozen_sim  want_retrieve
# Re-frozen for Qwen/Qwen3-Embedding-0.6B. The previous values belonged to
# snowflake-arctic-embed-m-v2.0, which was silently returning collapsed vectors
# (see docs/rework_actions.md) — under it these numbers did not separate at all:
# the highest-scoring case in the whole set (planner, 0.699) was a should-SKIP,
# while should-RETRIEVE topped out at 0.536. No threshold could have classified
# them, which is why the old 0.47 sat in a 0.036-wide gap and needed hand-tuning.
#
# Under the new model the set separates cleanly: every should-retrieve case
# (0.589-0.644) scores above every should-skip case (0.375-0.587).
GOLDEN_GATE = [
    ("planner (a spec)", PLANNER,                              0.509,  False),
    ("feature spec",     SPEC_0,                               0.457,  False),
    ("feature spec",     SPEC_1,                               0.375,  False),
    ("vague-but-real",   "Put this together in a testable UI and make it match the mock", 0.675, True),
    ("vague-but-real",   "Continue with filling endpoint integration gaps first",         0.644, True),
    ("open question",    "How should I structure the endpoint integrations across these data sources?", 0.636, True),
    ("terse-dense spec", TERSE_SPEC,                           0.451,  False),
    ("factual recall",   "What endpoints did you end up mapping",                          0.577, False),
    ("traceback",        TRACEBACK,                            0.587,  False),
]


# ---------------------------------------------------------------------------
# 1. The two-signal decision, hermetic (the separation signal we care about)
# ---------------------------------------------------------------------------
class TestBandDecision:
    """retrieve <=> sim >= SIM AND LOW <= words <= HIGH AND density <= D."""

    @pytest.mark.parametrize("label,text,sim,want", GOLDEN_GATE)
    def test_golden_separation(self, label, text, sim, want):
        dec = _band_decision(sim, len(text.split()),
                             specification_density(text), SIMILARITY_THRESHOLD)
        assert dec.search == want, (
            f"[{label}] want retrieve={want} got {dec.search}\n"
            f"  sim={sim} words={len(text.split())} "
            f"density={specification_density(text):.3f}\n  reason: {dec.reason}"
        )

    def test_high_similarity_spec_is_blocked_by_band_not_similarity(self):
        # the headline case: a spec is maximally on-topic yet must not retrieve.
        # similarity alone would pass it; the band is what stops it.
        dec = _band_decision(0.74, 180, 0.15, SIMILARITY_THRESHOLD)
        assert dec.search is False
        assert "too long" in dec.reason

    def test_terse_dense_spec_blocked_by_density_ceiling(self):
        # short enough to pass the word band, dense enough that the ceiling catches it
        dec = _band_decision(0.55, 9, 0.67, SIMILARITY_THRESHOLD)
        assert dec.search is False
        assert "already specified" in dec.reason

    def test_skip_reason_names_every_failed_signal(self):
        dec = _band_decision(0.40, 200, 0.30, 0.50)
        for fragment in ("no semantic match", "too long", "already specified"):
            assert fragment in dec.reason, dec.reason


# ---------------------------------------------------------------------------
# 2. Word-count band and density ceiling edges
# ---------------------------------------------------------------------------
class TestBandEdges:
    def test_word_band_boundaries(self):
        # in-band at both edges, out just past them; sim and density held clear
        assert _band_decision(0.9, WORD_BAND_LOW, 0.0, 0.5).search is True
        assert _band_decision(0.9, WORD_BAND_HIGH, 0.0, 0.5).search is True
        assert _band_decision(0.9, WORD_BAND_LOW - 1, 0.0, 0.5).search is False
        assert _band_decision(0.9, WORD_BAND_HIGH + 1, 0.0, 0.5).search is False

    def test_density_ceiling_boundary(self):
        mid = (WORD_BAND_LOW + WORD_BAND_HIGH) // 2
        assert _band_decision(0.9, mid, SPECIFICITY_THRESHOLD, 0.5).search is True
        assert _band_decision(0.9, mid, SPECIFICITY_THRESHOLD + 0.01, 0.5).search is False

    def test_similarity_boundary(self):
        mid = (WORD_BAND_LOW + WORD_BAND_HIGH) // 2
        assert _band_decision(0.50, mid, 0.0, 0.50).search is True
        assert _band_decision(0.49, mid, 0.0, 0.50).search is False


# ---------------------------------------------------------------------------
# 3. Stage-1 pre-filters still short-circuit before any embedding call
# ---------------------------------------------------------------------------
class TestPreFilters:
    def test_greeting_skips(self):
        d = _heuristic_check("hey there")
        assert d is not None and d.search is False and "greeting" in d.reason

    def test_followup_skips(self):
        d = _heuristic_check("looks good, thanks", recent_turns=["earlier turn"])
        assert d is not None and d.search is False

    def test_too_brief_skips(self):
        d = _heuristic_check("do that")
        assert d is not None and d.search is False and "too brief" in d.reason

    def test_real_request_passes_prefilters(self):
        # a genuine request must fall through to the band, not be pre-skipped
        assert _heuristic_check("How should I structure the integrations here") is None

    def test_specificity_is_no_longer_a_prefilter(self):
        # density used to skip here; it now lives only in the band, so a dense
        # message must pass the pre-filters and reach the embedding stage
        assert _heuristic_check(SPEC_0) is None


# ---------------------------------------------------------------------------
# 4. Removed memory overrides: drift can no longer force a search
# ---------------------------------------------------------------------------
class TestMemoryNoLongerForcesSearch:
    def test_high_drift_no_corpus_match_does_not_retrieve(self):
        # Constructing a frame needs the real contract, and arteries is not on
        # PyPI — so this one skips where it is absent (CI) and runs where the
        # sibling checkout is installed.
        pytest.importorskip("arteries.memory_types")
        from arteries.memory_types import (
            MemoryFrame, EphemeralMemory, PersistentMemory, EvergreenMemory,
        )
        frame = MemoryFrame(
            ephemeral=EphemeralMemory(topic_drift=0.9, turn_count=9),
            persistent=PersistentMemory(),
            evergreen=EvergreenMemory(),
        )
        # a message with no plausible corpus match — drift is high, but the old
        # code would (wrongly) force search on drift alone. Stub the embedding so
        # this stays hermetic.
        async def _no_match(_msg, _cfg=None):
            return 0.10, None
        import capillaries.agent.gate as g
        orig = g._embedding_proximity
        g._embedding_proximity = _no_match
        try:
            dec = run(gate("xxxxx yyyyy zzzzz qqqqq wwwww", context=frame))
        finally:
            g._embedding_proximity = orig
        assert dec.search is False, dec.reason


# ---------------------------------------------------------------------------
# 5. Confusion matrix — reporting only, always passes
# ---------------------------------------------------------------------------
class TestReport:
    def test_gate_confusion_matrix(self, capsys):
        tp = tn = fp = fn = 0
        rows = []
        for label, text, sim, want in GOLDEN_GATE:
            got = _band_decision(sim, len(text.split()),
                                specification_density(text), SIMILARITY_THRESHOLD).search
            rows.append((label, sim, len(text.split()),
                         specification_density(text), want, got))
            if want and got: tp += 1
            elif want and not got: fn += 1
            elif not want and got: fp += 1
            else: tn += 1
        with capsys.disabled():
            print(f"\n{'='*72}\nGATE CONFUSION MATRIX  (SIM={SIMILARITY_THRESHOLD} "
                  f"band={WORD_BAND_LOW}-{WORD_BAND_HIGH}w D={SPECIFICITY_THRESHOLD})")
            print(f"  retrieve: TP={tp} FN={fn}   skip: TN={tn} FP={fp}")
            print(f"  {'label':17}{'sim':>6}{'words':>6}{'dens':>6}  want  got")
            for label, sim, w, d, want, got in rows:
                flag = "" if want == got else "  <-- miss"
                print(f"  {label:17}{sim:6.3f}{w:6}{d:6.2f}  "
                      f"{'R' if want else 'skip':>4}  {'R' if got else 'skip':>4}{flag}")


# ---------------------------------------------------------------------------
# 6. Live: the frozen similarities still reflect the real corpus
# ---------------------------------------------------------------------------
@pytest.mark.db
class TestLiveGate:
    @pytest.mark.parametrize("label,text,frozen_sim,want", [
        r for r in GOLDEN_GATE if r[0] in ("planner (a spec)", "feature spec", "vague-but-real")
    ])
    def test_frozen_sims_still_hold(self, label, text, frozen_sim, want):
        from capillaries.agent.gate import _embedding_proximity
        sim, _ = run(_embedding_proximity(text))
        assert abs(sim - frozen_sim) < 0.08, (
            f"[{label}] corpus drift: frozen {frozen_sim:.3f}, now {sim:.3f}. "
            f"Re-freeze GOLDEN_GATE if this is an intentional corpus change."
        )

    def test_real_gate_skips_both_planner_and_spec(self):
        # both are fully-specified instructions and both must skip — a plexus run
        # retrieves nothing, which is correct: it is all specs, no open queries
        planner = run(gate(PLANNER))
        spec = run(gate(SPEC_0))
        assert planner.search is False, planner.reason
        assert spec.search is False, spec.reason

    def test_real_gate_retrieves_a_vague_interactive_query(self):
        # the case retrieval actually exists for
        d = run(gate("Continue with filling endpoint integration gaps first"))
        assert d.search is True, d.reason


# ---------------------------------------------------------------------------
# 6. Cached-retrieval overlap — hermetic, guards the skip that reuses a cache
# ---------------------------------------------------------------------------

class TestSituationOverlap:
    def test_paraphrase_of_cached_situation_still_matches(self):
        from capillaries.agent.gate import _situation_overlaps
        assert _situation_overlaps(
            "help me design the postgres retrieval schema",
            "designing the retrieval schema in postgres",
        )

    def test_incidental_stopword_overlap_does_not_match(self):
        from capillaries.agent.gate import _situation_overlaps
        # only stopwords + one content word shared — different tasks must not skip
        assert not _situation_overlaps(
            "how should i write the deployment script",
            "how should i review the marketing budget",
        )

    def test_single_shared_content_word_is_not_enough(self):
        from capillaries.agent.gate import _situation_overlaps
        assert not _situation_overlaps("optimize the reranker latency",
                                       "optimize the onboarding funnel copy")
