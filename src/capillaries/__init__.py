"""Capillaries — prompt search and management system with semantic retrieval."""

__all__ = ["find", "find_sync", "FindResult", "MemoryFrame"]


def __getattr__(name):
    # Lazy so importing capillaries for the contract types alone doesn't drag
    # in the retrieval stack. The types themselves now live in arteries, which
    # produces the frames; this re-export is a convenience, not the source.
    if name in __all__:
        from capillaries.find import find, find_sync, FindResult
        from arteries.memory_types import MemoryFrame
        globals().update(find=find, find_sync=find_sync,
                         FindResult=FindResult, MemoryFrame=MemoryFrame)
        return globals()[name]
    raise AttributeError(f"module 'capillaries' has no attribute {name!r}")
