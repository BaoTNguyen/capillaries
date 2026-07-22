"""
Text/code fence protection (STACK_READINESS §5.2).

Skills and prompts are text + code, and only the text is DSPy-optimizable.
Code improves through execution-verified episodes (a heart episode running
the skill's own check), never through a prompt optimizer — an optimizer that
rewrites a code fence is a hard failure, not a style choice.

split_fences() breaks markdown into an ordered list of (kind, text) segments:
  "prose"       — everything else
  "fence"       — a ``` ... ``` block, backtick lines included
  "frontmatter" — a leading --- ... --- block, if present, as its own segment

assert_fences_unchanged() compares the *ordered* fence/frontmatter segments
(byte-for-byte) between two versions of the same document and raises
ValueError naming the first one that diverged. Prose segments are excluded
from the comparison — that's the part the optimizer is allowed to touch.
"""

from __future__ import annotations

import re

_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)
_FENCE_RE = re.compile(r"^(```.*?\n.*?\n```[ \t]*$)", re.DOTALL | re.MULTILINE)


def split_fences(markdown: str) -> list[tuple[str, str]]:
    """
    Split markdown into ordered (kind, text) segments.

    kind is one of "prose", "fence", "frontmatter". Segment texts concatenate
    back to the original string exactly.
    """
    segments: list[tuple[str, str]] = []
    remainder = markdown

    fm_match = _FRONTMATTER_RE.match(remainder)
    if fm_match:
        segments.append(("frontmatter", fm_match.group(0)))
        remainder = remainder[fm_match.end():]

    pos = 0
    for m in re.finditer(r"```.*?\n.*?\n```", remainder, re.DOTALL):
        if m.start() > pos:
            segments.append(("prose", remainder[pos:m.start()]))
        segments.append(("fence", m.group(0)))
        pos = m.end()
    if pos < len(remainder):
        segments.append(("prose", remainder[pos:]))

    return segments


def _protected_segments(markdown: str) -> list[str]:
    """Ordered list of non-prose (frontmatter + fence) segment texts."""
    return [text for kind, text in split_fences(markdown) if kind != "prose"]


def assert_fences_unchanged(before: str, after: str) -> None:
    """
    Raise ValueError if the ordered protected (frontmatter/fence) segments
    differ between `before` and `after`, naming the first divergent fence.
    """
    before_fences = _protected_segments(before)
    after_fences = _protected_segments(after)

    if len(before_fences) != len(after_fences):
        raise ValueError(
            f"fence count changed: {len(before_fences)} -> {len(after_fences)}"
        )

    for i, (b, a) in enumerate(zip(before_fences, after_fences)):
        if b != a:
            preview = b.strip().splitlines()[0][:60] if b.strip() else "(empty)"
            raise ValueError(
                f"fence #{i} changed (optimizer touched protected content): {preview!r}"
            )
