"""
[A6] Semantic cache: serve a stored answer for a question that MEANS the same
as an earlier one, without calling the chat model at all.

How it works
  1. The question is turned into a vector by an embedding model (Ollama
     /api/embed). Two questions that mean the same have close vectors.
  2. The cache keeps (question vector, answer) rows in SQLite. A lookup is a
     cosine similarity against the rows that are allowed to answer this
     question; the best one above a threshold is a hit.
  3. On a miss the question is answered normally and, if it is safe to reuse
     (see Policy), the answer is stored for next time.

Why it is conservative: a wrong cache hit is worse than a slow answer. A row
is only reused for the same persona prompt + model, only within its scope
(per user by default), and never past its time to live. What may be cached
and what may be served is decided by the Policy functions below, not here.

Pure Python (array + math): a few hundred rows is a few milliseconds, no new
dependency. Rows are normalised on write, so a dot product is the cosine.
"""

import hashlib
import math
import os
import sqlite3
import time
from array import array
from dataclasses import dataclass

import requests

from Memories import Database


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in ("0", "false", "no", "off")


def _env_number(name: str, default: float, low: float, high: float) -> float:
    try:
        value = float(os.getenv(name, default))
    except ValueError:
        return default
    return value if low <= value <= high else default


ENABLED = _env_bool("CACHE_ENABLED", True)
EMBED_MODEL = os.getenv("CACHE_EMBED_MODEL", "nomic-embed-text").strip() or "nomic-embed-text"
SIMILARITY = _env_number("CACHE_SIMILARITY", 0.92, 0.5, 1.0)
TTL_HOURS = _env_number("CACHE_TTL_HOURS", 168, 0, 24 * 365)  # 0 = never expires
MAX_ENTRIES = int(_env_number("CACHE_MAX_ENTRIES", 500, 10, 100000))
# "user": a user only reuses their own answers (safe default for HR data).
# "global": every user shares the cache (best hit rate, only for non personal answers).
SCOPE = os.getenv("CACHE_SCOPE", "user").strip().lower()
if SCOPE not in ("user", "global"):
    SCOPE = "user"
# Only store answers produced with no earlier conversation behind them: they cannot
# depend on it. False = also store mid-conversation answers (more hits, some risk).
CONTEXT_FREE_ONLY = _env_bool("CACHE_CONTEXT_FREE_ONLY", True)


@dataclass
class Hit:
    answer: str
    similarity: float
    question: str


@dataclass
class Lookup:
    hit: Hit | None = None
    embedding: list[float] | None = None  # kept so a miss does not embed twice


class EmbeddingUnavailable(Exception):
    """The embedding model cannot be used (not installed...). Permanent for the process."""


def fingerprint(model: str, system_prompt: str) -> str:
    """Rows are only reused for the same model and the same persona prompt."""
    return hashlib.sha1(f"{model}\0{system_prompt}".encode("utf-8")).hexdigest()[:16]


def _normalise(vector: list[float]) -> list[float] | None:
    norm = math.sqrt(sum(x * x for x in vector))
    return [x / norm for x in vector] if norm > 0 else None


def _pack(vector: list[float]) -> bytes:
    return array("f", vector).tobytes()


def _unpack(blob: bytes) -> array:
    values = array("f")
    values.frombytes(blob)
    return values


class SemanticCache:
    def __init__(self, base_url: str, embed_model: str = None, threshold: float = None,
                 ttl_hours: float = None, scope: str = None, max_entries: int = None):
        self.base_url = base_url
        self.embed_model = embed_model or EMBED_MODEL
        self.threshold = SIMILARITY if threshold is None else threshold
        self.ttl_hours = TTL_HOURS if ttl_hours is None else ttl_hours
        self.scope = scope or SCOPE
        self.max_entries = max_entries or MAX_ENTRIES
        self.unavailable_reason: str | None = None  # set once the embedding model is unusable

    # -- storage -----------------------------------------------------------
    @staticmethod
    def _connect() -> sqlite3.Connection:
        conn = Database.get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS semantic_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope_key TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                question TEXT NOT NULL,
                embedding BLOB NOT NULL,
                answer TEXT NOT NULL,
                hits INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                last_used_at REAL NOT NULL
            )
        """)
        return conn

    def _scope_key(self, user_id: str) -> str:
        return user_id if self.scope == "user" else "*"

    def _expiry_cutoff(self) -> float:
        return 0.0 if self.ttl_hours <= 0 else time.time() - self.ttl_hours * 3600

    # -- embedding -----------------------------------------------------------
    def embed(self, text: str) -> list[float] | None:
        """Normalised vector, or None when it cannot be computed right now.
        Raises EmbeddingUnavailable when it never will be (model not installed)."""
        if self.unavailable_reason:
            raise EmbeddingUnavailable(self.unavailable_reason)
        try:
            response = requests.post(f"{self.base_url}/api/embed",
                                     json={"model": self.embed_model, "input": text}, timeout=15)
        except requests.exceptions.RequestException:
            return None  # transient: just no cache for this turn
        if response.status_code in (400, 404):
            self.unavailable_reason = (f"embedding model '{self.embed_model}' is not available "
                                       f"(ollama pull {self.embed_model})")
            raise EmbeddingUnavailable(self.unavailable_reason)
        try:
            response.raise_for_status()
            vector = response.json()["embeddings"][0]
            return _normalise([float(x) for x in vector])
        except (requests.exceptions.RequestException, KeyError, IndexError, TypeError, ValueError):
            return None

    # -- API ---------------------------------------------------------------
    def lookup(self, user_id: str, fp: str, question: str, serve: bool = True) -> Lookup:
        """Embed the question and look for a close, allowed, unexpired answer.
        serve=False only computes the embedding (the question may be stored but not served)."""
        vector = self.embed(question)
        if vector is None or not serve:
            return Lookup(None, vector)
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, question, embedding, answer FROM semantic_cache "
                "WHERE scope_key = ? AND fingerprint = ? AND created_at >= ?",
                (self._scope_key(user_id), fp, self._expiry_cutoff())).fetchall()
            best, best_score = None, 0.0
            for row in rows:
                stored = _unpack(row["embedding"])
                if len(stored) != len(vector):
                    continue  # another embedding model wrote it
                score = sum(a * b for a, b in zip(vector, stored))
                if score > best_score:
                    best, best_score = row, score
            if best is None or best_score < self.threshold:
                return Lookup(None, vector)
            conn.execute("UPDATE semantic_cache SET hits = hits + 1, last_used_at = ? WHERE id = ?",
                         (time.time(), best["id"]))
            conn.commit()
            return Lookup(Hit(best["answer"], best_score, best["question"]), vector)
        finally:
            conn.close()

    def store(self, user_id: str, fp: str, question: str, vector: list[float], answer: str) -> None:
        conn = self._connect()
        try:
            now = time.time()
            scope_key = self._scope_key(user_id)
            # Same question again (e.g. after the entry expired or the policy changed): refresh it.
            conn.execute("DELETE FROM semantic_cache WHERE scope_key = ? AND fingerprint = ? AND question = ?",
                         (scope_key, fp, question))
            conn.execute(
                "INSERT INTO semantic_cache (scope_key, fingerprint, question, embedding, answer, "
                "created_at, last_used_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (scope_key, fp, question, _pack(vector), answer, now, now))
            # Bound the size: drop expired rows, then the least recently used.
            conn.execute("DELETE FROM semantic_cache WHERE created_at < ?", (self._expiry_cutoff(),))
            conn.execute(
                "DELETE FROM semantic_cache WHERE id IN (SELECT id FROM semantic_cache "
                "ORDER BY last_used_at DESC LIMIT -1 OFFSET ?)", (self.max_entries,))
            conn.commit()
        finally:
            conn.close()

    def clear(self, user_id: str | None = None) -> int:
        """Empty the cache (everything, or one user's rows). Returns the number of rows removed."""
        conn = self._connect()
        try:
            if user_id is None or self.scope == "global":
                cursor = conn.execute("DELETE FROM semantic_cache")
            else:
                cursor = conn.execute("DELETE FROM semantic_cache WHERE scope_key = ?", (user_id,))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    def stats(self, user_id: str | None = None) -> dict:
        conn = self._connect()
        try:
            where, args = "", ()
            if user_id is not None and self.scope == "user":
                where, args = "WHERE scope_key = ?", (user_id,)
            row = conn.execute(f"SELECT COUNT(*) AS n, COALESCE(SUM(hits), 0) AS hits "
                               f"FROM semantic_cache {where}", args).fetchone()
            return {"entries": row["n"], "hits": row["hits"], "scope": self.scope,
                    "threshold": self.threshold, "ttl_hours": self.ttl_hours,
                    "embed_model": self.embed_model}
        finally:
            conn.close()
