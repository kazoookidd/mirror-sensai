"""
[R2] Benchmark of the reranking of the RAG (results: docs/benchmarks/rag_reranking.md).

data/docs is indexed with the project's own pipeline, then each question of Bench_embeddings.py
is retrieved with the project's Retriever, three ways:
  - embeddings only (RAG_KEYWORD_WEIGHT=0), as before R2;
  - hybrid: the embedding candidates scored again with their keywords (BM25), at several weights;
  - LLM: the chat model orders the 10 embedding candidates itself (measured here, not used by Sensai).
A question is answered well when its document comes first. The final score of the right
passage, against the best off-topic one, shows how well the threshold drops near-misses.

Usage (from the project root, Ollama running, models pulled):
    python back/benchmarks/Bench_rerank.py bge-m3 nomic-embed-text --chat-model qwen2.5:3b
"""

import argparse
import os
import re
import sys
import tempfile
import time
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import requests

from Bench_embeddings import OFF_TOPIC, QUESTIONS, sources_ranked
from Memories import Database
from rag import Retriever, Store

WEIGHTS = (0.0, 0.1, 0.15, 0.25, 0.35)
CANDIDATES = 10
LLM_PROMPT = (
    "Question : {question}\n\nPassages :\n{passages}\n\n"
    "Réponds uniquement par les numéros des passages utiles pour répondre à la question, du plus utile au "
    "moins utile, séparés par des virgules (par exemple : 3, 1). Si aucun n'est utile, réponds : aucun."
)


def retrieve_all(question: str, base_url: str, weight: float) -> list[dict]:
    with mock.patch.dict(os.environ, {"RAG_KEYWORD_WEIGHT": str(weight)}):
        return Retriever.retrieve(question, ollama_url=base_url)


def llm_order(question: str, candidates: list[dict], base_url: str, chat_model: str) -> tuple[list[dict], list[int]]:
    """The candidates in the order the chat model gives (the ones it leaves out come after)."""
    passages = "\n".join(f"[{i + 1}] {c['text'][:400]}" for i, c in enumerate(candidates))
    body = {"model": chat_model, "stream": False, "options": {"temperature": 0},
            "messages": [{"role": "user", "content": LLM_PROMPT.format(question=question, passages=passages)}]}
    answer = requests.post(f"{base_url}/api/chat", json=body, timeout=300).json()["message"]["content"]
    picked = [int(n) - 1 for n in re.findall(r"\d+", answer) if 0 < int(n) <= len(candidates)]
    picked = list(dict.fromkeys(picked))
    return [candidates[i] for i in picked] + [c for i, c in enumerate(candidates) if i not in picked], picked


def rank_of(expected: str, chunks: list[dict]) -> int:
    ranked = sources_ranked(chunks)
    return ranked.index(expected) + 1 if expected in ranked else 99


def summary(ranks: list[int], right: list[float], off: list[float], times: list[float]) -> dict:
    return {"hit1": sum(r == 1 for r in ranks), "hit3": sum(r <= 3 for r in ranks), "n": len(ranks),
            "mrr": sum(1 / r for r in ranks if r != 99) / len(ranks),
            "right_min": min(right) if right else None, "off_max": max(off) if off else None,
            "ms": 1000 * float(np.median(times))}


def bench(model: str, base_url: str, chat_model: str | None) -> dict:
    env = {"RAG_EMBED_MODEL": model, "RAG_MIN_SCORE": "-1", "RAG_TOP_K": "1000", "RAG_CANDIDATES": str(CANDIDATES)}
    patches = [mock.patch.dict(os.environ, env),
               mock.patch.object(Database, "DB_PATH", os.path.join(tempfile.mkdtemp(), "bench.db"))]
    for patch in patches:
        patch.start()
    try:
        Database.init_db()
        Store.index_directory(Store.DEFAULT_DOCS_DIR)
        results = {}
        for weight in WEIGHTS:
            ranks, right, times = [], [], []
            for question, expected in QUESTIONS:
                start = time.monotonic()
                chunks = retrieve_all(question, base_url, weight)
                times.append(time.monotonic() - start)
                ranks.append(rank_of(expected, chunks))
                right.append(max((c["score"] for c in chunks if c["source"] == expected), default=0.0))
            off = [retrieve_all(q, base_url, weight)[0]["score"] for q in OFF_TOPIC]
            results[f"hybrid {weight:g}" if weight else "embeddings only"] = summary(ranks, right, off, times)
        if chat_model:
            ranks, times, off_kept = [], [], 0
            for question, expected in QUESTIONS:
                candidates = retrieve_all(question, base_url, 0.0)[:CANDIDATES]
                start = time.monotonic()
                ordered, _ = llm_order(question, candidates, base_url, chat_model)
                times.append(time.monotonic() - start)
                ranks.append(rank_of(expected, ordered))
            for question in OFF_TOPIC:
                _, picked = llm_order(question, retrieve_all(question, base_url, 0.0)[:CANDIDATES], base_url, chat_model)
                off_kept += bool(picked)
            llm = summary(ranks, [], [], times)
            llm["off_kept"] = off_kept
            results[f"LLM ({chat_model})"] = llm
        return results
    finally:
        for patch in reversed(patches):
            patch.stop()


def table(model: str, results: dict) -> str:
    rows = [f"### {model}", "",
            "| Method | Right document 1st | In the top 3 | MRR | Right passage, lowest score | Off-topic, highest score | Gap | Time (median) |",
            "|---|---|---|---|---|---|---|---|"]
    for name, r in results.items():
        gap = f"{r['right_min'] - r['off_max']:.3f}" if r["right_min"] is not None else f"{r.get('off_kept', 0)}/{len(OFF_TOPIC)} off-topic questions kept passages"
        right = f"{r['right_min']:.3f}" if r["right_min"] is not None else "-"
        off = f"{r['off_max']:.3f}" if r["off_max"] is not None else "-"
        rows.append(f"| {name} | {r['hit1']}/{r['n']} | {r['hit3']}/{r['n']} | {r['mrr']:.2f} | {right} | {off} | {gap} | {r['ms']:.0f} ms |")
    return "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(description="Benchmark of the RAG reranking")
    parser.add_argument("models", nargs="+", help="embedding models to compare")
    parser.add_argument("--chat-model", help="also measure the reranking by this chat model")
    parser.add_argument("--ollama-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    args = parser.parse_args()
    for model in args.models:
        print(f"{model}...", file=sys.stderr)
        print(table(model, bench(model, args.ollama_url, args.chat_model)) + "\n")


if __name__ == "__main__":
    main()
