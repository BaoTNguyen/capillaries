"""Capillaries — prompt search and management system with semantic retrieval."""

__all__ = ["find", "find_sync", "FindResult", "MemoryFrame"]


def __getattr__(name):
    # Lazy so importing capillaries for the contract types alone doesn't drag
    # in the retrieval stack. The types themselves now live in arteries, which
    # produces the frames; this re-export is a convenience, not the source.
    #
    # The two groups resolve separately. Fetching them together meant
    # `from capillaries import find` — the first example in the README — pulled
    # in arteries and raised ModuleNotFoundError without it, even though
    # capillaries.find imports fine on its own. Retrieval must not depend on
    # the memory contract being installed.
    if name == "MemoryFrame":
        try:
            from arteries.memory_types import MemoryFrame
        except ModuleNotFoundError as exc:
            raise AttributeError(
                "capillaries.MemoryFrame re-exports arteries.memory_types.MemoryFrame, "
                "and arteries is not installed. It is not on PyPI — install the "
                "sibling checkout with `pip install -e ../arteries`. Retrieval "
                "(find, find_sync, FindResult) works without it."
            ) from exc
        globals()["MemoryFrame"] = MemoryFrame
        return MemoryFrame

    if name in __all__:
        from capillaries.find import find, find_sync, FindResult
        globals().update(find=find, find_sync=find_sync, FindResult=FindResult)
        return globals()[name]

    raise AttributeError(f"module 'capillaries' has no attribute {name!r}")
