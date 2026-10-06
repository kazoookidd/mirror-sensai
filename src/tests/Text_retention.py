"""
Standalone retention test for [M2] Token Budgeting & Semantic Compression.

Not part of the interactive chatbot: this script seeds a dedicated test
conversation with known facts, forces compression with an artificially
small budget, then asks the model questions requiring those facts and
scores how many were correctly retained.

Usage:
    python src/tests/Text_retention.py
    python src/tests/Text_retention.py --model llama3 --filler-rounds 15
"""

import argparse
import os
import sys
from dotenv import load_dotenv

# src/tests/Text_retention.py -> one level up is src/, which is what
# needs to be on sys.path for "Memories.X" imports to resolve, exactly
# like Chatbot.py does.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Memories.Database import init_db, get_connection
from Memories.Auth import get_or_create_user
from Memories.Memory import save_message
from Memories.Conversations import create_conversation
from Memories.Compression import build_context, get_compression_stats

TEST_USER_ID = "retention_test_user"
TEST_EMAIL = "retention_test@example.com"
TEST_PASSWORD = "retention_test_password"

# Facts injected early in the conversation, and the keyword(s) that must
# appear in the model's answer for that fact to count as "retained".
FACTS = [
    {
        "statement": "Le nom du projet est Atlas.",
        "question": "Quel est le nom du projet ?",
        "expected_keywords": ["atlas"],
    },
    {
        "statement": "La deadline du projet est le 15 novembre.",
        "question": "Quelle est la deadline du projet ?",
        "expected_keywords": ["15 novembre", "novembre"],
    },
    {
        "statement": "Le projet utilise PostgreSQL comme base de données.",
        "question": "Quelle base de données utilise le projet ?",
        "expected_keywords": ["postgresql", "postgres"],
    },
    {
        "statement": "Alice est responsable du projet.",
        "question": "Qui est responsable du projet ?",
        "expected_keywords": ["alice"],
    },
]


def reset_test_user():
    """Wipe any previous run for the test account so results are
    reproducible, without touching any other user's data."""
    conn = get_connection()
    try:
        conn.execute("""
            DELETE FROM messages WHERE conversation_id IN (
                SELECT id FROM conversations WHERE user_id = ?
            )
        """, (TEST_USER_ID,))
        conn.execute("""
            DELETE FROM summaries WHERE conversation_id IN (
                SELECT id FROM conversations WHERE user_id = ?
            )
        """, (TEST_USER_ID,))
        conn.execute("DELETE FROM compression_logs WHERE user_id = ?", (TEST_USER_ID,))
        conn.execute("DELETE FROM conversations WHERE user_id = ?", (TEST_USER_ID,))
        conn.execute("DELETE FROM users WHERE user_id = ?", (TEST_USER_ID,))
        conn.commit()
    finally:
        conn.close()


def seed_conversation(conversation_id: int, filler_rounds: int):
    """Inject the known facts, then enough filler exchanges to push the
    history past the (artificially small) compression threshold."""
    for fact in FACTS:
        save_message(conversation_id, "user", fact["statement"])
        save_message(conversation_id, "assistant", "Compris, c'est noté.")

    for i in range(filler_rounds):
        save_message(
            conversation_id, "user",
            f"Parlons d'autre chose, point de discussion numero {i}. " * 3
        )
        save_message(
            conversation_id, "assistant",
            f"D'accord, voici une réponse générique numero {i}. " * 3
        )


def ask(conversation_id: int, model: str, base_url: str,
        system_prompt: str, question: str) -> str:
    """Build the (possibly compressed) context and ask a single question,
    non-streaming, for easy scoring. Returns an empty string (counted as
    a missed fact) if Ollama cannot be reached, instead of crashing the
    whole test run."""
    import requests

    context = build_context(conversation_id, system_prompt, model, base_url)
    context.append({"role": "user", "content": question})

    try:
        response = requests.post(
            f"{base_url}/api/chat",
            json={"model": model, "messages": context, "stream": False},
            timeout=120
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"[Error: could not reach Ollama for this question - {e}]")
        return ""

    return response.json().get("message", {}).get("content", "")


def score_answer(answer: str, expected_keywords: list[str]) -> bool:
    answer_lower = answer.lower()
    return any(keyword.lower() in answer_lower for keyword in expected_keywords)


def main():
    parser = argparse.ArgumentParser(description="M2 retention test")
    parser.add_argument("--model", default=os.getenv("MODEL", "llama3"))
    parser.add_argument("--ollama-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    parser.add_argument("--filler-rounds", type=int, default=15,
                         help="Number of filler exchanges to force compression")
    parser.add_argument("--budget", type=int, default=300,
                         help="Artificially small token budget to trigger compression quickly")
    parser.add_argument("--threshold-ratio", type=float, default=0.5)
    parser.add_argument("--keep-last-n", type=int, default=4)
    args = parser.parse_args()

    load_dotenv()
    init_db()

    print("=== M2 Retention Test ===\n")

    import requests
    try:
        requests.get(args.ollama_url, timeout=5)
    except requests.exceptions.RequestException:
        print(f"Error: cannot reach Ollama at {args.ollama_url}. "
              f"Is it running? (ollama serve)")
        return

    reset_test_user()
    get_or_create_user(TEST_USER_ID, TEST_PASSWORD, email=TEST_EMAIL)
    conversation_id = create_conversation(TEST_USER_ID, title="Retention test")
    seed_conversation(conversation_id, args.filler_rounds)

    system_prompt = "You are a helpful assistant."

    # Force at least one compression pass up front, using the small test
    # budget, so the questions below are genuinely answered from a
    # compressed context rather than raw history.
    build_context(
        conversation_id, system_prompt, args.model, args.ollama_url,
        budget=args.budget, threshold_ratio=args.threshold_ratio,
        keep_last_n=args.keep_last_n
    )

    results = []
    for fact in FACTS:
        answer = ask(conversation_id, args.model, args.ollama_url, system_prompt, fact["question"])
        retained = score_answer(answer, fact["expected_keywords"])
        results.append({
            "question": fact["question"],
            "answer": answer,
            "retained": retained,
        })

    stats = get_compression_stats(conversation_id)
    retained_count = sum(1 for r in results if r["retained"])

    print("--- Answers ---")
    for r in results:
        mark = "OK" if r["retained"] else "MISSED"
        print(f"[{mark}] {r['question']}")
        print(f"   -> {r['answer'].strip()[:150]}")
    print()

    print("--- Compression stats ---")
    print(f"Total compressions : {stats['total_compressions']}")
    print(f"Tokens saved       : {stats['tokens_saved']}")
    print(f"Average ratio      : {stats['avg_ratio']:.1%}")
    print(f"Total duration (s) : {stats['total_duration']:.2f}")
    print()

    print("--- Retention ---")
    print(f"Facts tested    : {len(FACTS)}")
    print(f"Facts retained  : {retained_count}/{len(FACTS)}")
    print(f"Retention rate  : {retained_count / len(FACTS):.1%}")


if __name__ == "__main__":
    main()