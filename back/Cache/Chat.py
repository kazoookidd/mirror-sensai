"""
Glue between the chat loop and the semantic cache: two calls in chat_turn.

    turn = check(session, user_input)       # BEFORE building any context
    if turn.hit: ...print it, save the exchange, done: no compression,
                 no RAG search, no model call
    ...answer normally...
    remember(session, turn, user_input, answer, used_tools=..., had_history=...)

The cache never breaks a turn: any problem (embedding model missing, Ollama
slow, database error) means "no cache for this turn".
"""

import sqlite3
from dataclasses import dataclass

from Cache import Policy
from Cache.SemanticCache import (ENABLED, EmbeddingUnavailable, Hit, Lookup,
                                 SemanticCache, fingerprint)

_caches: dict[tuple, SemanticCache] = {}


def get_cache(session) -> SemanticCache:
    """One cache object per Ollama server (it remembers an unusable embedding model)."""
    key = (session.ollama_url,)
    if key not in _caches:
        _caches[key] = SemanticCache(session.ollama_url)
    return _caches[key]


def enabled(session) -> bool:
    return ENABLED and getattr(session, "semantic_cache", True)


@dataclass
class CacheTurn:
    hit: Hit | None = None
    lookup: Lookup | None = None  # carries the embedding to store a miss
    fp: str = ""


def check(session, user_input: str) -> CacheTurn:
    if not enabled(session):
        return CacheTurn()
    cache = get_cache(session)
    if cache.unavailable_reason:
        return CacheTurn()
    # The persona prompt AND the user's profile [M1]: a new tone or language must not reuse old answers.
    fp = fingerprint(session.model, session.system_prompt)
    # A question that may not be SERVED can still be STORED later, but only if it
    # passes the same rules; if it does not, skip the embedding altogether.
    if not Policy.may_serve(user_input):
        return CacheTurn(fp=fp)
    try:
        lookup = cache.lookup(session.user_id, fp, user_input)
    except EmbeddingUnavailable as e:
        session.out.note(f"[semantic cache off: {e}]")
        return CacheTurn()
    except sqlite3.Error:
        return CacheTurn()
    return CacheTurn(lookup.hit, lookup, fp)


def hit_note(hit: Hit) -> str:
    return (f"  · answered from the cache ({hit.similarity:.0%} similar to an earlier question, "
            f"no model call)")


def remember(session, turn: CacheTurn, user_input: str, answer: str, *,
             used_tools: bool, had_history: bool) -> None:
    if turn.lookup is None or turn.lookup.embedding is None or turn.hit is not None:
        return
    from Cache.SemanticCache import CONTEXT_FREE_ONLY
    if not Policy.may_store(user_input, answer, used_tools=used_tools, had_history=had_history,
                            context_free_only=CONTEXT_FREE_ONLY):
        return
    try:
        get_cache(session).store(session.user_id, turn.fp, user_input, turn.lookup.embedding, answer)
    except sqlite3.Error:
        pass


def invalidate() -> int:
    """Forget everything: call it when the knowledge the answers rely on changes (/ingest)."""
    try:
        return SemanticCache("").clear()
    except sqlite3.Error:
        return 0
