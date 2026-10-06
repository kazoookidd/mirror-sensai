import os
import time
import requests
from dotenv import load_dotenv

from .Database import get_connection
from .Memory import load_history_with_ids
from .Conversations import get_conversation

load_dotenv()  # ensures env vars are available even if this module is
               # imported before Chatbot.py calls load_dotenv() itself

DEFAULT_BUDGET = int(os.getenv("CONTEXT_TOKEN_BUDGET", "4000"))
DEFAULT_THRESHOLD_RATIO = float(os.getenv("CONTEXT_THRESHOLD_RATIO", "0.8"))
DEFAULT_KEEP_LAST_N = int(os.getenv("CONTEXT_KEEP_LAST_N", "10"))

CHARS_PER_TOKEN = 4  # crude approximation, good enough to trigger compression


def estimate_tokens(text: str) -> int:
    """Rough token count estimate: ~4 characters per token.
    Ollama does not expose a generic tokenizer over HTTP, so this is a
    deliberate approximation, only used to decide WHEN to compress,
    not for billing or exact context-window enforcement."""
    if not text:
        return 0
    return max(1, len(text) // CHARS_PER_TOKEN)


# ---------------------------------------------------------------------
# Summary state (current, one row per conversation)
# ---------------------------------------------------------------------

def get_summary(conversation_id: int) -> dict | None:
    """Return the current cached summary for a conversation, or None if
    it doesn't have one yet."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT summary_text, covers_up_to_msg_id, token_count "
            "FROM summaries WHERE conversation_id = ?",
            (conversation_id,)
        ).fetchone()
        if row is None:
            return None
        return {
            "summary_text": row["summary_text"],
            "covers_up_to_msg_id": row["covers_up_to_msg_id"],
            "token_count": row["token_count"],
        }
    finally:
        conn.close()


def save_summary(conversation_id: int, summary_text: str, covers_up_to_msg_id: int) -> None:
    """Upsert the current summary for a conversation. Overwrites any
    previous summary - only one active summary per conversation is kept,
    by design."""
    token_count = estimate_tokens(summary_text)
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO summaries (conversation_id, summary_text, covers_up_to_msg_id,
                                    token_count, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(conversation_id) DO UPDATE SET
                summary_text = excluded.summary_text,
                covers_up_to_msg_id = excluded.covers_up_to_msg_id,
                token_count = excluded.token_count,
                updated_at = CURRENT_TIMESTAMP
        """, (conversation_id, summary_text, covers_up_to_msg_id, token_count))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------
# Compression metrics (append-only)
# ---------------------------------------------------------------------

def log_compression(conversation_id: int, user_id: str, tokens_before: int,
                     tokens_after: int, messages_compressed: int,
                     summary_token_count: int, duration_seconds: float) -> None:
    """Record one compression event for later reporting (keynote, dashboards).
    user_id is denormalized so cross-conversation stats for a user don't
    require a join."""
    ratio = 1 - (tokens_after / tokens_before) if tokens_before else 0.0
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO compression_logs
                (conversation_id, user_id, tokens_before, tokens_after,
                 compression_ratio, messages_compressed, summary_token_count,
                 duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (conversation_id, user_id, tokens_before, tokens_after, ratio,
              messages_compressed, summary_token_count, duration_seconds))
        conn.commit()
    finally:
        conn.close()


def get_compression_stats(conversation_id: int) -> dict:
    """Aggregate stats across all compression events for one conversation -
    handy for a quick report without re-reading every row manually."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) AS total_compressions,
                COALESCE(SUM(tokens_before - tokens_after), 0) AS tokens_saved,
                COALESCE(AVG(compression_ratio), 0) AS avg_ratio,
                COALESCE(SUM(duration_seconds), 0) AS total_duration
            FROM compression_logs WHERE conversation_id = ?
        """, (conversation_id,)).fetchone()
        return {
            "total_compressions": row["total_compressions"],
            "tokens_saved": row["tokens_saved"],
            "avg_ratio": row["avg_ratio"],
            "total_duration": row["total_duration"],
        }
    finally:
        conn.close()


def get_compression_stats_for_user(user_id: str) -> dict:
    """Aggregate stats across ALL of a user's conversations - useful for
    a global dashboard rather than a single conversation's report."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT
                COUNT(*) AS total_compressions,
                COALESCE(SUM(tokens_before - tokens_after), 0) AS tokens_saved,
                COALESCE(AVG(compression_ratio), 0) AS avg_ratio,
                COALESCE(SUM(duration_seconds), 0) AS total_duration
            FROM compression_logs WHERE user_id = ?
        """, (user_id,)).fetchone()
        return {
            "total_compressions": row["total_compressions"],
            "tokens_saved": row["tokens_saved"],
            "avg_ratio": row["avg_ratio"],
            "total_duration": row["total_duration"],
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------
# Summarization call (internal, non-streaming - not user-facing)
# ---------------------------------------------------------------------

def _summarize_with_ollama(base_url: str, model: str,
                            existing_summary: str | None,
                            messages: list[dict]) -> str:
    """Ask the model to produce a single consolidated summary from the
    existing summary (if any) plus a batch of older messages. Raises
    RuntimeError on any failure so the caller can decide on a fallback."""
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in messages)

    if existing_summary:
        instruction = (
            "You are maintaining a running summary of a conversation. "
            "Merge the EXISTING SUMMARY below with the NEW MESSAGES into "
            "a single, consolidated summary. Preserve every concrete fact "
            "(names, dates, numbers, decisions). Be concise but do not "
            "drop information. Respond with the summary only, no preamble."
            f"\n\nEXISTING SUMMARY:\n{existing_summary}"
            f"\n\nNEW MESSAGES:\n{transcript}"
        )
    else:
        instruction = (
            "Summarize the following conversation excerpt. Preserve every "
            "concrete fact (names, dates, numbers, decisions). Be concise "
            "but do not drop information. Respond with the summary only, "
            "no preamble."
            f"\n\nMESSAGES:\n{transcript}"
        )

    try:
        response = requests.post(
            f"{base_url}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": instruction}],
                "stream": False
            },
            timeout=120
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Summarization call failed: {e}")

    data = response.json()
    summary = data.get("message", {}).get("content", "").strip()
    if not summary:
        raise RuntimeError("Summarization call returned empty content.")
    return summary


# ---------------------------------------------------------------------
# Context Builder - the public entry point used by Chatbot.py
# ---------------------------------------------------------------------

def build_context(conversation_id: int, system_prompt: str, model: str,
                   base_url: str, budget: int = None,
                   threshold_ratio: float = None,
                   keep_last_n: int = None) -> list[dict]:
    """
    Build the message list to send to Ollama for the NEXT turn, based on
    one conversation's stored history only (the current, not-yet-saved
    user input is NOT included here - the caller appends it after this
    call).

    Behavior:
    - Loads the cached summary for this conversation (if any) and only
      the messages stored AFTER it (covers_up_to_msg_id), never
      reprocessing old ground.
    - If the estimated token count stays under the threshold, returns
      the summary (if any) + all those messages untouched.
    - If it exceeds the threshold, keeps the last `keep_last_n` messages
      intact and asks the model to fold everything older (existing
      summary + the rest) into one consolidated summary, then persists
      it and logs a compression event.
    - On any summarization failure, falls back to keeping only the last
      `keep_last_n` messages without a summary, rather than crashing
      the turn.
    """
    budget = budget if budget is not None else DEFAULT_BUDGET
    threshold_ratio = (
        threshold_ratio if threshold_ratio is not None else DEFAULT_THRESHOLD_RATIO
    )
    keep_last_n = keep_last_n if keep_last_n is not None else DEFAULT_KEEP_LAST_N
    threshold = budget * threshold_ratio

    summary_row = get_summary(conversation_id)
    since_id = summary_row["covers_up_to_msg_id"] if summary_row else 0
    summary_text = summary_row["summary_text"] if summary_row else None

    all_history = load_history_with_ids(conversation_id)
    new_messages = [m for m in all_history if m["id"] > since_id]

    total_tokens = estimate_tokens(system_prompt)
    if summary_text:
        total_tokens += estimate_tokens(summary_text)
    total_tokens += sum(estimate_tokens(m["content"]) for m in new_messages)

    def _wrap_system(prompt: str, summary: str | None) -> dict:
        if summary:
            return {
                "role": "system",
                "content": f"{prompt}\n\n--- Résumé des échanges précédents ---\n{summary}"
            }
        return {"role": "system", "content": prompt}

    # --- No compression needed ---
    if total_tokens < threshold or len(new_messages) <= keep_last_n:
        context = [_wrap_system(system_prompt, summary_text)]
        context.extend({"role": m["role"], "content": m["content"]} for m in new_messages)
        return context

    # --- Compression needed ---
    to_summarize = new_messages[:-keep_last_n]
    to_keep = new_messages[-keep_last_n:]
    tokens_before = total_tokens

    try:
        start = time.time()
        new_summary_text = _summarize_with_ollama(
            base_url, model, summary_text, to_summarize
        )
        duration = time.time() - start
    except RuntimeError as e:
        # Safety net: don't crash the conversation if summarization fails.
        # Drop the old messages without summarizing them (they remain
        # safe in SQLite) and keep going with just the recent ones.
        print(f"\n[Warning: context compression failed, falling back "
              f"to recent messages only - {e}]")
        context = [_wrap_system(system_prompt, summary_text)]
        context.extend({"role": m["role"], "content": m["content"]} for m in to_keep)
        return context

    last_summarized_id = to_summarize[-1]["id"]
    save_summary(conversation_id, new_summary_text, last_summarized_id)

    tokens_after = estimate_tokens(system_prompt) + estimate_tokens(new_summary_text)
    tokens_after += sum(estimate_tokens(m["content"]) for m in to_keep)

    conversation = get_conversation(conversation_id)
    owner_user_id = conversation["user_id"] if conversation else "unknown"

    log_compression(
        conversation_id=conversation_id,
        user_id=owner_user_id,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        messages_compressed=len(to_summarize),
        summary_token_count=estimate_tokens(new_summary_text),
        duration_seconds=duration,
    )

    context = [_wrap_system(system_prompt, new_summary_text)]
    context.extend({"role": m["role"], "content": m["content"]} for m in to_keep)
    return context