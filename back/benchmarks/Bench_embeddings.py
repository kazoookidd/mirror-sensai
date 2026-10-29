"""
Benchmark of the embedding models on Sensai's HR documents (results: docs/benchmarks/embedding_models.md).

RAG: data/docs is indexed with the project's own pipeline (Loader, Chunker, Store), then
each question below is retrieved with the project's Retriever. A question is answered
well when the document it comes from is among the chunks retrieved. Off-topic questions
measure how high a wrong match scores, to choose RAG_MIN_SCORE.
Cache: pairs of questions that mean the same, or not, are compared as the semantic cache
does (raw text, cosine), to choose CACHE_SIMILARITY.

Usage (from the project root, Ollama running, models pulled):
    python back/benchmarks/Bench_embeddings.py nomic-embed-text bge-m3 bge-m3:noprefix

A name ending in ":noprefix" embeds without the "search_document: " / "search_query: "
prefixes that rag/Embeddings.py adds (they are made for nomic-embed-text).
"""

import argparse
import os
import sys
import tempfile
import time
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import requests

from Memories import Database
from rag import Embeddings, Retriever, Store

CURRENT_MIN_SCORE = 0.70
CURRENT_CACHE_SIMILARITY = 0.92
TOP_K = 3  # RAG_TOP_K

QUESTIONS = [
    ("Combien de jours de congé pour un mariage ?", "loi_conge_mariage_pacs.md"),
    ("Je me pacse, ai-je droit à des jours de congé ?", "loi_conge_mariage_pacs.md"),
    ("Le congé pour mariage est-il déduit de mes congés payés ?", "loi_conge_mariage_pacs.md"),
    ("Mon père est décédé, combien de jours d'absence puis-je prendre ?", "loi_conge_deces.md"),
    ("Ai-je droit à un congé si mon frère meurt ?", "loi_conge_deces.md"),
    ("Combien de jours de congés payés j'acquiers chaque mois ?", "loi_conges_payes.md"),
    ("Un apprenti a-t-il droit à des congés payés ?", "loi_conges_payes.md"),
    ("Est-ce que j'acquiers des congés payés pendant un arrêt maladie ?", "loi_conges_payes.md"),
    ("Quelles sont les dates des jours fériés en 2026 ?", "loi_jours_feries.txt"),
    ("Le 1er mai est-il obligatoirement chômé ?", "loi_jours_feries.txt"),
    ("Noël 2027 tombe quel jour de la semaine ?", "loi_jours_feries.txt"),
    ("Comment mettre en place le télétravail ?", "loi_teletravail.md"),
    ("Mon employeur peut-il refuser ma demande de télétravail ?", "loi_teletravail.md"),
    ("Dans quels lieux peut-on télétravailler ?", "loi_teletravail.md"),
    ("Le règlement intérieur est-il obligatoire dans une entreprise de 30 salariés ?", "loi_reglement_interieur.md"),
    ("Quelles clauses sont interdites dans un règlement intérieur ?", "loi_reglement_interieur.md"),
    ("La mutuelle d'entreprise est-elle obligatoire pour l'employeur ?", "loi_complementaire_sante.md"),
    ("Quelles garanties minimales doit couvrir la complémentaire santé ?", "loi_complementaire_sante.md"),
    ("Quelle augmentation de salaire prévoit l'accord NAO 2026 ?", "syd_accord_nao_2026.pdf"),
    ("Quel est le montant de la prime de cooptation ?", "syd_accord_nao_2026.pdf"),
    ("Quand la prime de vacances est-elle versée ?", "syd_accord_nao_2026.pdf"),
    ("Si je verse 300 € sur mon épargne salariale, combien l'entreprise ajoute-t-elle ?", "syd_accord_nao_2026.pdf"),
]

OFF_TOPIC = [
    "Quelle est la recette de la pizza ?",
    "Qui a gagné la Coupe du monde de football 2018 ?",
    "Comment installer Python sur Linux ?",
    "Quel temps fera-t-il demain à Nantes ?",
    "Écris un poème sur la mer.",
    "Quelle est la capitale de l'Australie ?",
]

# (question, question, same meaning?) for the semantic cache
PAIRS = [
    ("Comment poser un jour de congé payé ?", "Quelle est la démarche pour prendre un congé payé ?", True),
    ("Combien de jours pour un mariage ?", "J'ai droit à combien de jours si je me marie ?", True),
    ("Le télétravail est-il un droit ?", "Puis-je exiger de télétravailler ?", True),
    ("Quand est versée la prime de vacances ?", "À quelle date touche-t-on la prime de vacances ?", True),
    ("La mutuelle est-elle obligatoire ?", "Suis-je obligé d'adhérer à la mutuelle d'entreprise ?", True),
    ("Combien de jours pour un mariage ?", "Combien de jours pour un décès ?", False),
    ("Combien de jours de congés payés par mois ?", "Combien de jours fériés par an ?", False),
    ("Quand est versée la prime de vacances ?", "Quel est le montant de la prime de cooptation ?", False),
    ("Le télétravail est-il un droit ?", "Le télétravail est-il remboursé ?", False),
    ("Combien de jours pour un mariage ?", "Combien de jours pour un Pacs ?", False),
]


def sources_ranked(chunks: list[dict]) -> list[str]:
    """The documents of the retrieved chunks, best first, each once."""
    return list(dict.fromkeys(chunk["source"] for chunk in chunks))


def raw_cosine(base_url: str, model: str, a: str, b: str) -> float:
    vectors = requests.post(f"{base_url}/api/embed", json={"model": model, "input": [a, b]}, timeout=120).json()["embeddings"]
    a, b = np.asarray(vectors[0]), np.asarray(vectors[1])
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b)))


def bench(variant: str, base_url: str) -> dict:
    model, no_prefix = (variant[:-len(":noprefix")], True) if variant.endswith(":noprefix") else (variant, False)
    patches = [mock.patch.dict(os.environ, {"RAG_EMBED_MODEL": model, "RAG_MIN_SCORE": "-1", "RAG_TOP_K": "1000"}),
               mock.patch.object(Database, "DB_PATH", os.path.join(tempfile.mkdtemp(), "bench.db"))]
    if no_prefix:
        patches += [mock.patch.object(Embeddings, "DOCUMENT_PREFIX", ""), mock.patch.object(Embeddings, "QUERY_PREFIX", "")]
    for patch in patches:
        patch.start()
    try:
        Database.init_db()
        start = time.monotonic()
        stats = Store.index_directory(Store.DEFAULT_DOCS_DIR)
        index_seconds = time.monotonic() - start

        ranks, hit_scores, query_times = [], [], []
        for question, expected in QUESTIONS:
            start = time.monotonic()
            chunks = Retriever.retrieve(question, ollama_url=base_url)
            query_times.append(time.monotonic() - start)
            top = chunks[:TOP_K]
            ranks.append(sources_ranked(chunks).index(expected) + 1 if expected in sources_ranked(chunks) else 99)
            best_right = max((c["score"] for c in chunks if c["source"] == expected), default=0.0)
            hit_scores.append(best_right if any(c["source"] == expected for c in top) else None)
        off_scores = [Retriever.retrieve(q, ollama_url=base_url)[0]["score"] for q in OFF_TOPIC]
    finally:
        for patch in reversed(patches):
            patch.stop()

    right = [s for s in hit_scores if s is not None]
    same = [raw_cosine(base_url, model, a, b) for a, b, alike in PAIRS if alike]
    different = [raw_cosine(base_url, model, a, b) for a, b, alike in PAIRS if not alike]
    return {
        "variant": variant, "chunks": stats["chunks"], "index_s": index_seconds,
        "hit1": sum(r == 1 for r in ranks), "hit3": sum(r <= TOP_K for r in ranks), "n": len(ranks),
        "mrr": sum(1 / r for r in ranks if r != 99) / len(ranks), "query_ms": 1000 * float(np.median(query_times)),
        "right_min": min(right, default=0.0), "right_median": float(np.median(right)) if right else 0.0,
        "off_max": max(off_scores), "off_median": float(np.median(off_scores)),
        "kept_at_current": sum(s >= CURRENT_MIN_SCORE for s in right), "off_kept_at_current": sum(s >= CURRENT_MIN_SCORE for s in off_scores),
        "same_min": min(same), "same_median": float(np.median(same)),
        "diff_max": max(different), "diff_median": float(np.median(different)),
        "cache_hits_at_current": sum(s >= CURRENT_CACHE_SIMILARITY for s in same),
        "cache_wrong_at_current": sum(s >= CURRENT_CACHE_SIMILARITY for s in different),
        "misses": [q for (q, _), r in zip(QUESTIONS, ranks) if r > TOP_K],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="+")
    parser.add_argument("--ollama-url", default=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    options = parser.parse_args()
    results = []
    for variant in options.models:
        print(f"{variant}...", file=sys.stderr)
        results.append(bench(variant, options.ollama_url))

    print("### Retrieval (RAG)\n")
    print("| Model | Chunks | Indexing | Right document 1st | Right document in top 3 | MRR | Query (median) |")
    print("|---|---|---|---|---|---|---|")
    for r in results:
        print(f"| {r['variant']} | {r['chunks']} | {r['index_s']:.1f} s | {r['hit1']}/{r['n']} | **{r['hit3']}/{r['n']}** | "
              f"{r['mrr']:.2f} | {r['query_ms']:.0f} ms |")
    print("\n### Scores, to choose RAG_MIN_SCORE\n")
    print(f"| Model | Right chunk: min / median | Off-topic best: median / max | Kept at {CURRENT_MIN_SCORE} (right) | "
          f"Kept at {CURRENT_MIN_SCORE} (off-topic) |")
    print("|---|---|---|---|---|")
    for r in results:
        print(f"| {r['variant']} | {r['right_min']:.3f} / {r['right_median']:.3f} | {r['off_median']:.3f} / {r['off_max']:.3f} | "
              f"{r['kept_at_current']}/{r['hit3']} | {r['off_kept_at_current']}/{len(OFF_TOPIC)} |")
    print("\n### Semantic cache, to choose CACHE_SIMILARITY\n")
    print(f"| Model | Same meaning: min / median | Different meaning: median / max | Served at {CURRENT_CACHE_SIMILARITY} "
          f"(same) | Served at {CURRENT_CACHE_SIMILARITY} (different = wrong answer) |")
    print("|---|---|---|---|---|")
    n_same = sum(alike for *_, alike in PAIRS)
    for r in results:
        print(f"| {r['variant']} | {r['same_min']:.3f} / {r['same_median']:.3f} | {r['diff_median']:.3f} / {r['diff_max']:.3f} | "
              f"{r['cache_hits_at_current']}/{n_same} | {r['cache_wrong_at_current']}/{len(PAIRS) - n_same} |")
    print("\n### Questions whose document is not in the top 3\n")
    for r in results:
        print(f"- {r['variant']}: " + ("; ".join(r["misses"]) or "none"))


if __name__ == "__main__":
    main()
