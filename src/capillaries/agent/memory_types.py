"""
Memory types consumed by capillaries.

These dataclasses define the contract between the memory project (arteries)
and capillaries's retrieval/gating layer. The memory project owns all
write/eviction/scoring logic — capillaries only reads these frames.

Separated into their own module to avoid pulling in heavy ML dependencies
(torch, sentence-transformers) at import time.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Insight:
    text: str
    source: str
    domain: str | None = None
    confidence: float = 1.0


@dataclass
class CachedRetrieval:
    prompt_id: str
    situation: str
    score: float
    relevance: float = 1.0


@dataclass
class EphemeralMemory:
    recent_messages: list[str] = field(default_factory=list)
    topic_drift: float = 0.0
    turn_count: int = 0


@dataclass
class PersistentMemory:
    session_insights: list[Insight] = field(default_factory=list)
    prior_retrievals: list[CachedRetrieval] = field(default_factory=list)
    active_domains: list[str] = field(default_factory=list)


@dataclass
class EvergreenMemory:
    user_intent: list[str] = field(default_factory=list)
    recurring_domains: list[str] = field(default_factory=list)
    ground_truth_insights: list[Insight] = field(default_factory=list)
    last_retrieval_ts: float | None = None
    retrieval_confidence: float | None = None


@dataclass
class MemoryFrame:
    ephemeral: EphemeralMemory = field(default_factory=EphemeralMemory)
    persistent: PersistentMemory = field(default_factory=PersistentMemory)
    evergreen: EvergreenMemory = field(default_factory=EvergreenMemory)
