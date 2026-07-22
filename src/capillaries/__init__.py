"""Capillaries — prompt search and management system with semantic retrieval."""

__all__ = ["find", "find_sync", "FindResult", "MemoryFrame"]


def __getattr__(name):
    # Lazy so `import capillaries.agent.memory_types` (the contract types
    # arteries needs on every hook turn) doesn't drag in the retrieval stack.
    if name in __all__:
        from capillaries.find import find, find_sync, FindResult
        from capillaries.agent.memory_types import MemoryFrame
        globals().update(find=find, find_sync=find_sync,
                         FindResult=FindResult, MemoryFrame=MemoryFrame)
        return globals()[name]
    raise AttributeError(f"module 'capillaries' has no attribute {name!r}")
