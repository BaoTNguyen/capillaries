"""
Gating mechanism for agent routing.

Two-stage filter that decides whether a user message warrants a prompt search.
Stage 1: fast heuristic checks (0ms) — kills obvious skips.
Stage 2: embedding proximity check (~40ms) — semantic corpus match.

When a MemoryFrame is provided, the gate uses memory signals (topic drift,
cached retrievals, domain alignment, user intent) to modulate its decision.
The memory project owns all write logic — the gate only reads the frame.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from capillaries.agent.memory_types import (  # noqa: F401 — re-export for backward compat
    Insight,
    CachedRetrieval,
    EphemeralMemory,
    PersistentMemory,
    EvergreenMemory,
    MemoryFrame,
)

QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
MAX_CHARS = 4_000

# Retrieve only when a message clears BOTH signals: it has a real semantic match
# to the corpus AND it is neither too simple nor too complicated. The two are
# complementary, not redundant — measured on real traffic, each is decisive
# exactly where the other is blind:
#   - a fully-specified spec scores HIGH similarity (0.61-0.74) but is out of the
#     complexity band, so similarity alone would wrongly retrieve it (this is the
#     "Delegate Like a Parallel Coworker" false positive);
#   - a vague-but-real request sits IN the band but scores below the similarity
#     bar, so the band alone would retrieve a prompt that doesn't fit.
# Type is not consulted — a question, a command and a paste are judged the same
# way, on these two signals.
# 0.47 sits in the narrow gap between the queries worth retrieving and the ones
# not: on labelled traffic, open questions land ~0.498 and meta-questions about
# prior work ("what did you map?") ~0.462, so 0.47 catches the former and rejects
# the latter. The gap is real but small — no single cut fully separates them,
# since embedding can't tell "how should I do X" from "what did you do about X" —
# so this is the one genuinely tunable knob; the word/density signals separate
# cleanly and don't move.
SIMILARITY_THRESHOLD = float(os.getenv("CAPILLARIES_SIMILARITY_THRESHOLD", "0.47"))

# "not too simple / not too complicated" — a word-count band with a second,
# density-based ceiling. Both ceilings earn their place: HIGH catches long
# low-density prose dumps; the density ceiling catches the terse-but-fully-decided
# spec (e.g. 9 words naming file, signature and expected value at density 0.67)
# that slips under HIGH. Calibrated on labelled messages: want-retrieve span
# 7-42 words at density <=0.02; feature specs 116-211 words at density 0.11-0.20.
WORD_BAND_LOW = int(os.getenv("CAPILLARIES_WORD_BAND_LOW", "5"))
WORD_BAND_HIGH = int(os.getenv("CAPILLARIES_WORD_BAND_HIGH", "60"))
SPECIFICITY_THRESHOLD = float(os.getenv("CAPILLARIES_SPECIFICITY_THRESHOLD", "0.08"))

_SPEC_TOKEN = re.compile(r"""
      \w+/[\w./-]+                 # a/b/c.py paths
    | \w+\.(py|js|ts|json|toml|md|txt|sh|yaml|yml|rs|go)\b
    | \w+\([^)]*\)                  # call(...) or signature(s: str)
    | \w+_\w+                      # snake_case identifiers
    | [A-Z]{2,}[A-Z_]*=            # ENV_VAR=
    | --?[a-zA-Z][\w-]+            # --flags
    | ==|!=|->|=>|>=|<=            # assertions and arrows
    | `[^`]+`                      # inline code
    | "[^"]{1,40}"|'[^']{1,40}'    # short literals, usually expected values
""", re.VERBOSE)

def specification_density(message: str) -> float:
    """Fraction of tokens that encode an already-made decision.

    High means the caller has done the deciding: paths, signatures, expected
    values, flags. Low means the message states an intent and leaves the how
    open — which is what a prompt library can actually help with.
    """
    tokens = message.split()
    if not tokens:
        return 0.0
    return len(_SPEC_TOKEN.findall(message)) / len(tokens)

WORKFLOW_VERBS = frozenset({
    "build", "create", "design", "develop", "implement", "write",
    "debug", "fix", "troubleshoot", "diagnose", "resolve",
    "review", "audit", "evaluate", "assess", "analyze", "compare",
    "plan", "strategize", "outline", "architect", "map",
    "optimize", "improve", "refactor", "restructure", "migrate",
    "test", "validate", "verify", "benchmark",
    "deploy", "launch", "ship", "release",
    "document", "explain", "summarize",
    "research", "investigate", "explore",
    "generate", "draft", "compose", "produce",
})

FOLLOWUP_PATTERNS = frozenset({
    "yes", "no", "yeah", "yep", "nope", "nah",
    "ok", "okay", "sure", "thanks", "thank you", "thx",
    "got it", "makes sense", "sounds good", "looks good",
    "perfect", "great", "nice", "cool", "awesome",
    "do it", "go ahead", "proceed", "continue",
    "agreed", "correct", "right", "exactly",
    "nevermind", "never mind", "nvm", "cancel",
})

CASUAL_PATTERNS = re.compile(
    r"^(hi|hello|hey|good morning|good afternoon|good evening|what's up|howdy|sup)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Gate decision
# ---------------------------------------------------------------------------


@dataclass
class GateDecision:
    search: bool
    confidence: float
    reason: str

    def to_dict(self) -> dict:
        return {
            "search": self.search,
            "confidence": round(self.confidence, 3),
            "reason": self.reason,
        }


def _has_workflow_verb(text: str) -> bool:
    words = set(re.findall(r"[a-z]+", text.lower()))
    return bool(words & WORKFLOW_VERBS)


def _is_followup(message: str, recent_turns: list[str] | None = None) -> bool:
    normalized = message.strip().lower().rstrip("!?.,")
    if normalized in FOLLOWUP_PATTERNS:
        return True
    if recent_turns and len(recent_turns) >= 1 and len(normalized.split()) <= 3:
        return True
    return False


def _is_casual_greeting(message: str) -> bool:
    return bool(CASUAL_PATTERNS.match(message.strip()))


def _heuristic_check(message: str, recent_turns: list[str] | None = None) -> GateDecision | None:
    """
    Stage 1: fast heuristic checks. Returns a skip decision or None to continue.
    """
    stripped = message.strip()

    if _is_casual_greeting(stripped):
        return GateDecision(search=False, confidence=0.95, reason="casual greeting")

    if _is_followup(stripped, recent_turns):
        return GateDecision(search=False, confidence=0.90, reason="conversational followup")

    words = stripped.split()
    if len(words) < 5 and not _has_workflow_verb(stripped):
        return GateDecision(search=False, confidence=0.80, reason="too brief, no action signal")

    return None


def _band_decision(sim: float, words: int, density: float,
                   threshold: float) -> GateDecision:
    """The two-signal gate, as a pure function of the three measured values.

    retrieve  <=>  sim >= threshold  AND  LOW <= words <= HIGH  AND  density <= D

    Kept free of I/O so the whole decision layer is unit-testable without a
    database or embedding endpoint. Every failed sub-condition is named in the
    skip reason, so a skipped message says exactly which signal stopped it.
    """
    fails = []
    if sim < threshold:
        fails.append(f"no semantic match (sim={sim:.2f}<{threshold:.2f})")
    if words < WORD_BAND_LOW:
        fails.append(f"too simple ({words}w<{WORD_BAND_LOW})")
    if words > WORD_BAND_HIGH:
        fails.append(f"too long ({words}w>{WORD_BAND_HIGH})")
    if density > SPECIFICITY_THRESHOLD:
        fails.append(f"already specified (density={density:.2f}>{SPECIFICITY_THRESHOLD:.2f})")
    if fails:
        # confidence is how sure we are of the *skip*: a clear miss on similarity
        # is a confident skip, a marginal one is not
        return GateDecision(search=False, confidence=round(1.0 - sim, 3),
                            reason="; ".join(fails))
    return GateDecision(search=True, confidence=round(sim, 3),
                        reason=f"semantic match (sim={sim:.2f}), in complexity band")


async def _embedding_proximity(message: str, db_config: dict | None = None) -> tuple[float, str | None]:
    """
    Stage 2: embed the message and check nearest-neighbor similarity in the corpus.
    Returns (max_similarity, closest_title).
    """
    import httpx
    import psycopg2
    from capillaries.config import DB_CONFIG, EMBED_URL, EMBED_MODEL
    from capillaries.search.retriever import expand_acronyms

    config = db_config or DB_CONFIG

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            EMBED_URL,
            json={"input": QUERY_PREFIX + expand_acronyms(message)[:MAX_CHARS], "model": EMBED_MODEL},
            timeout=15.0,
        )
        if resp.status_code != 200:
            return 0.0, None
        query_vec = resp.json()["data"][0]["embedding"]

    conn = psycopg2.connect(**config)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT title,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM prompts
                WHERE embedding IS NOT NULL
                  AND status = 'active'
                ORDER BY embedding <=> %s::vector
                LIMIT 1
                """,
                (query_vec, query_vec),
            )
            row = cur.fetchone()
            if row:
                return float(row[1]), row[0]
            return 0.0, None
    finally:
        conn.close()


def _check_memory_frame(memory: MemoryFrame, message: str) -> GateDecision | None:
    """Memory can only SKIP here, never force a search.

    The old topic-drift and stale-context branches forced `search=True` on drift
    alone — which could retrieve for a message with no corpus match at all,
    contradicting the rule that retrieval requires a semantic match. They are
    gone. The one surviving signal is the cached-retrieval skip: if a recent
    retrieval already covers this situation, don't retrieve again.
    """
    for cached in memory.persistent.prior_retrievals:
        if cached.relevance > 0.75 and cached.score > 0.7:
            if _situation_overlaps(message.lower(), cached.situation):
                return GateDecision(
                    search=False,
                    confidence=cached.relevance,
                    reason=f"cached retrieval covers this (prompt={cached.prompt_id}, relevance={cached.relevance:.2f})",
                )
    return None


def _situation_overlaps(message: str, situation: str) -> bool:
    """Quick lexical overlap check between current message and a cached situation."""
    msg_words = set(re.findall(r"[a-z]{3,}", message))
    sit_words = set(re.findall(r"[a-z]{3,}", situation.lower()))
    if not msg_words or not sit_words:
        return False
    overlap = len(msg_words & sit_words) / min(len(msg_words), len(sit_words))
    return overlap > 0.5


async def gate(
    message: str,
    recent_turns: list[str] | None = None,
    memory: MemoryFrame | None = None,
    db_config: dict | None = None,
    threshold: float | None = None,
) -> GateDecision:
    """
    Decide whether a user message warrants a prompt search.

    Args:
        message: The current user message.
        recent_turns: Recent conversation messages for followup detection.
            Ignored when memory.ephemeral.recent_messages is populated.
        memory: MemoryFrame from the memory project. When provided, the gate
            uses memory signals (topic drift, cached retrievals, domain
            alignment) alongside heuristic and embedding checks.
        db_config: Database config override.
        threshold: Similarity threshold override.

    Returns:
        GateDecision with search (bool), confidence (float), and reason (str).
    """
    turns = recent_turns
    if memory and memory.ephemeral.recent_messages:
        turns = memory.ephemeral.recent_messages

    heuristic_result = _heuristic_check(message, turns)
    if heuristic_result is not None:
        return heuristic_result

    # Memory-based decision (takes priority over raw embedding proximity)
    if memory:
        memory_result = _check_memory_frame(memory, message)
        if memory_result is not None:
            return memory_result

    if threshold is None:
        threshold = SIMILARITY_THRESHOLD
        # Active domains in persistent memory signal ongoing work — lower the bar
        if memory and memory.persistent.active_domains:
            threshold -= 0.05

    try:
        max_sim, closest_id = await _embedding_proximity(message, db_config)
    except Exception:
        return GateDecision(
            search=True,
            confidence=0.5,
            reason="embedding check failed, defaulting to search",
        )

    decision = _band_decision(
        max_sim, len(message.split()), specification_density(message), threshold)
    # thread the matched prompt through when we're going to search, for the log
    if decision.search and closest_id is not None:
        decision.reason += f", closest={closest_id}"
    return decision
