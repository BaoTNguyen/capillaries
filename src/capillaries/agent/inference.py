"""
Inference module for extracting structured fields from freeform situation text.

Uses keyword heuristics and taxonomy matching to infer domain and intent.
Falls back to defaults when confidence is low.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

DOMAINS = ["AI", "business", "career", "finance", "learning", "personal", "product", "strategy", "technical", "writing"]
INTENT_KEYWORDS = {
    "build": ["build", "create", "implement", "develop", "make", "construct", "design", "setup", "architect"],
    "debug": ["debug", "fix", "troubleshoot", "error", "bug", "crash", "issue", "problem", "wrong", "fails", "broken"],
    "analyze": ["analyze", "review", "examine", "evaluate", "assess", "audit", "check", "understand", "investigate", "explore"],
    "improve": ["improve", "optimize", "enhance", "refactor", "upgrade", "better", "faster", "more efficient"],
    "document": ["document", "write", "explain", "describe", "spec", "specification", "guide", "tutorial"],
    "plan": ["plan", "strategy", "roadmap", "approach", "decide", "choose", "prioritize"],
    "test": ["test", "verify", "validate", "qa", "quality", "check"],
    "deploy": ["deploy", "release", "ship", "launch", "publish", "push"],
    "security": ["security", "vulnerability", "secure", "auth", "permission", "access", "protect"],
    "data": ["data", "database", "query", "sql", "transform", "pipeline", "etl"],
}

DOMAIN_KEYWORDS = {
    "technical": ["code", "programming", "software", "api", "server", "database", "docker", "kubernetes", "devops", "infrastructure", "backend", "frontend", "web", "app", "algorithm", "system", "architecture", "python", "javascript", "java", "go", "rust", "sql", "linux", "git", "testing", "debugging", "refactor"],
    "AI": ["ai", "machine learning", "ml", "model", "llm", "gpt", "embedding", "training", "inference", "prompt", "rag", "vector", "nlp", "neural", "deep learning", "transformer", "classification", "clustering"],
    "business": ["business", "revenue", "growth", "market", "customer", "sales", "marketing", "strategy", "company", "enterprise", "roi", "kpi", "metric", "budget", "cost", "pricing"],
    "strategy": ["strategy", "strategic", "roadmap", "vision", "goal", "objective", "planning", "competitive", "advantage", "positioning"],
    "product": ["product", "feature", "user experience", "ux", "ui", "design", "requirement", "specification", "roadmap", "launch"],
    "finance": ["finance", "financial", "investment", "budget", "cost", "revenue", "profit", "pricing", "valuation", "financial model", "forecast", "cash flow"],
    "career": ["career", "job", "resume", "interview", "promotion", "salary", "skills", "professional", "development", "leadership"],
    "learning": ["learn", "study", "education", "course", "training", "knowledge", "skill", "practice", "teach"],
    "personal": ["personal", "life", "habit", "goal", "productivity", "health", "wellness", "organization"],
    "writing": ["write", "writing", "content", "copy", "blog", "article", "documentation", "story", "narrative"],
}

@dataclass
class InferenceResult:
    domain: list[str]
    intent: list[str]


def infer_from_situation(situation: str, explicit_domain: list[str] | None = None, explicit_intent: list[str] | None = None) -> InferenceResult:
    """
    Infer structured fields from the situation text.

    Explicit values override inference for that field.
    """
    text = situation.lower()

    if explicit_domain:
        domain = explicit_domain
    else:
        domain = _infer_domain(text)

    if explicit_intent:
        intent = explicit_intent
    else:
        intent = _infer_intent(text)

    return InferenceResult(domain=domain, intent=intent)


def _infer_domain(text: str) -> list[str]:
    """Infer domain(s) from text using keyword matching."""
    scores: dict[str, float] = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[domain] = score

    if not scores:
        return ["technical"]

    sorted_domains = sorted(scores.keys(), key=lambda d: scores[d], reverse=True)
    top_domains = [sorted_domains[0]]
    if len(sorted_domains) > 1 and scores[sorted_domains[1]] >= scores[sorted_domains[0]] * 0.7:
        top_domains.append(sorted_domains[1])

    return top_domains


def _infer_intent(text: str) -> list[str]:
    """Infer intent(s) from text using keyword matching."""
    scores: dict[str, float] = {}
    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[intent] = score

    if not scores:
        return ["build"]

    sorted_intents = sorted(scores.keys(), key=lambda i: scores[i], reverse=True)
    return sorted_intents[:2]