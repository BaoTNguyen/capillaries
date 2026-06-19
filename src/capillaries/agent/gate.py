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

SIMILARITY_THRESHOLD = 0.50

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
    """Evaluate memory signals. Returns a decision if memory is conclusive, else None."""
    eph = memory.ephemeral
    per = memory.persistent
    evg = memory.evergreen

    # High topic drift — conversation has shifted, worth searching
    if eph.topic_drift > 0.3:
        return GateDecision(
            search=True,
            confidence=eph.topic_drift,
            reason=f"topic drift ({eph.topic_drift:.2f}) exceeds threshold",
        )

    # Check prior_retrievals — similar situation already handled recently
    msg_lower = message.lower()
    for cached in per.prior_retrievals:
        if cached.relevance > 0.75 and cached.score > 0.7:
            if _situation_overlaps(msg_lower, cached.situation):
                return GateDecision(
                    search=False,
                    confidence=cached.relevance,
                    reason=f"cached retrieval covers this (prompt={cached.prompt_id}, relevance={cached.relevance:.2f})",
                )

    # Many turns without retrieval + moderate drift — passive trigger
    if eph.turn_count > 5 and eph.topic_drift > 0.15:
        return GateDecision(
            search=True,
            confidence=0.6,
            reason=f"stale context ({eph.turn_count} turns, drift={eph.topic_drift:.2f})",
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

    if max_sim < threshold:
        return GateDecision(
            search=False,
            confidence=1.0 - max_sim,
            reason=f"no corpus match (similarity={max_sim:.3f}, threshold={threshold})",
        )

    return GateDecision(
        search=True,
        confidence=max_sim,
        reason=f"corpus match found (similarity={max_sim:.3f}, closest={closest_id})",
    )
