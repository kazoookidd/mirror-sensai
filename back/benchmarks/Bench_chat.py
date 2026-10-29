"""
Benchmark of the chat models on Sensai's own scenarios (results: docs/benchmarks/chat_models.md).

Every run goes through the real pipeline: chat_turn, the HR system prompt, the RAG over
data/docs, the ReAct agent and its tools, the human-in-the-loop leave request. Only two
things are not real: the database is a temporary file, and the web search returns a
fixed result (offline and the same for every model; its figure is made up on purpose,
so an answer that quotes it can only come from the tool).

Usage (from the project root, Ollama running, models pulled):
    python back/benchmarks/Bench_chat.py qwen2.5:3b qwen3:4b qwen3:4b:nothink qwen2.5:7b --runs 3

A name ending in ":nothink" runs that model with Ollama's "think": false (qwen3 only).
"""

import argparse
import io
import json
import os
import queue
import re
import sys
import tempfile
import time
from contextlib import redirect_stdout
from datetime import date
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import requests

import Chatbot
from Agents.ReAct import FRENCH_DAYS
from Memories import Database
from Memories.Auth import create_user
from Memories.Conversations import create_conversation
from rag import Store
from Web.Output import SseOutput

SEARCH_RESULT = [{"title": "SMIC 2026 : le nouveau montant",
                  "url": "https://example.org/smic-2026",
                  "snippet": "Au 1er janvier 2026, le SMIC horaire brut est de 12,34 euros (valeur de test)."}]


def today_fr() -> str:
    return FRENCH_DAYS[date.today().weekday()]


def has(text: str, *patterns: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


FRENCH = (r"\b(le|la|les|des|est|vous|pour)\b",)

# name, question, check(result) -> (passed, detail)
SCENARIOS = [
    ("date", "on est quel jour ?",
     lambda r: (has(r["answer"], rf"\b{today_fr()}\b") and not r["calls"],
                f"answer names {today_fr()}, no tool")),
    ("no tool", "Explique la différence entre un CDD et un CDI en trois phrases.",
     lambda r: (not r["calls"] and has(r["answer"], *FRENCH) and has(r["answer"], r"CDI") and len(r["answer"]) > 80,
                "no tool, French answer about CDI/CDD")),
    ("RAG (md)", "Combien de jours de congé ai-je pour mon mariage ?",
     lambda r: (has(r["answer"], r"\b4\b", r"quatre"), "4 days, from loi_conge_mariage_pacs.md")),
    ("RAG (pdf)", "Quel est le montant de la prime de cooptation pour le recrutement d'un CDI ?",
     lambda r: (has(r["answer"], r"2\s?000", r"deux mille"), "2 000 €, from the NAO agreement (PDF)")),
    ("leave (A3)", "Je pose du 3 au 7 novembre 2026 pour des vacances.",
     lambda r: (r["pending"] is not None and r["pending_args"] == {
         "leave_type": "paid_leave", "start_date": "2026-11-03", "end_date": "2026-11-07"},
                "paid_leave 2026-11-03 → 2026-11-07, waiting for /confirm")),
    ("web search", "Quel est le montant actuel du SMIC horaire brut ?",
     lambda r: ("search_internet" in r["calls"] and has(r["answer"], r"12[,.]34"),
                "searches, then quotes the result (12,34)")),
]


class TimedOutput(SseOutput):
    """The web output, with the time of each event."""

    def __init__(self):
        super().__init__(queue.Queue())
        self.log = []

    def _emit(self, name, **data):
        self.log.append((time.monotonic(), name, data))


def shown_answer(log) -> str:
    """The answer as the web interface shows it at the end (see useChat.js)."""
    text = ""
    for _, name, data in log:
        if name == "token":
            text += data["text"]
        elif name == "answer":
            text = data["text"]
        elif name == "retract" or (name == "trace" and data["kind"] == "thought"):
            text = ""
    return text


def run_once(session, question: str) -> dict:
    session.conversation_id = create_conversation(session.user_id, "bench")
    session.pending_action = None
    session.out = TimedOutput()
    calls, leave_args = [], {}
    originals = {name: tool.func for name, tool in session.tools.tools.items()}

    def recorder(name, func):
        def wrapped(**kwargs):
            calls.append(name)
            if name == "file_leave_request":
                leave_args.update({k: v for k, v in kwargs.items() if k != "reason"})
            return func(**kwargs)
        return wrapped

    for name, func in originals.items():
        session.tools.tools[name].func = recorder(name, func)
    start = time.monotonic()
    try:
        with redirect_stdout(io.StringIO()):
            ok = Chatbot.chat_turn(session, question)
    finally:
        for name, func in originals.items():
            session.tools.tools[name].func = func
    end = time.monotonic()
    log = session.out.log
    first = next((t for t, name, _ in log if name in ("token", "answer", "confirmation")), end)
    usage = next((d for _, name, d in log if name == "usage"), {})
    return {"ok": ok, "answer": shown_answer(log), "calls": calls, "pending": session.pending_action,
            "pending_args": leave_args or None, "first": first - start, "total": end - start,
            "prompt_tokens": usage.get("prompt"), "completion_tokens": usage.get("completion")}


def no_think(post):
    """requests.post with "think": false added to the chat calls (qwen3 thinks by default)."""
    def wrapped(url, json=None, **kwargs):
        if url.endswith("/api/chat") and json is not None:
            json = {**json, "think": False}
        return post(url, json=json, **kwargs)
    return wrapped


def unload(base_url: str, model: str) -> None:
    """Free the RAM before the next model (the machine has no GPU)."""
    try:
        requests.post(f"{base_url}/api/generate", json={"model": model, "keep_alive": 0}, timeout=60)
    except requests.RequestException:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="+")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--json", help="also write every run to this JSON file")
    options = parser.parse_args()

    tmp = tempfile.mkdtemp()
    Database.DB_PATH = os.path.join(tmp, "bench.db")
    Database.init_db()
    create_user("bench", "bench@example.com", "benchmark")
    print(f"Indexing data/docs with {os.getenv('RAG_EMBED_MODEL') or 'nomic-embed-text'}...", file=sys.stderr)
    print(Store.index_directory(Store.DEFAULT_DOCS_DIR), file=sys.stderr)

    rows, raw = [], []
    for variant in options.models:
        model, think_off = (variant[:-len(":nothink")], True) if variant.endswith(":nothink") else (variant, False)
        args = Chatbot.build_parser().parse_args(["--model", model])
        with redirect_stdout(io.StringIO()):
            session = Chatbot.build_session(args, "bench", None)
        session.semantic_cache = False
        patches = [mock.patch("Tools.web_search.search_internet", return_value=SEARCH_RESULT)]
        if think_off:
            patches.append(mock.patch.object(Chatbot.requests, "post", no_think(requests.post)))
        for patch in patches:
            patch.start()
        try:
            Chatbot.call_ollama(session.ollama_url, model, [{"role": "user", "content": "ok"}],
                                echo=False, options={"num_predict": 1}, on_error=lambda e: None)  # load it
            for name, question, check in SCENARIOS:
                for run in range(options.runs):
                    result = run_once(session, question)
                    passed, detail = check(result)
                    passed = passed and result["ok"]
                    print(f"{variant:18} {name:11} run {run + 1}: {'PASS' if passed else 'fail'} "
                          f"{result['first']:5.1f}s / {result['total']:5.1f}s  calls={result['calls']}  "
                          f"{result['answer'][:90]!r}", file=sys.stderr)
                    rows.append((variant, name, passed, result["first"], result["total"]))
                    raw.append({"model": variant, "scenario": name, "run": run + 1, "passed": passed,
                                "expected": detail, **{k: v for k, v in result.items() if k != "pending"}})
        finally:
            for patch in patches:
                patch.stop()
            unload(session.ollama_url, model)

    print("| Model | " + " | ".join(name for name, _, _ in SCENARIOS) + " | Total | First token (median) | Whole answer (median) |")
    print("|---" * (len(SCENARIOS) + 4) + "|")
    for variant in options.models:
        mine = [r for r in rows if r[0] == variant]
        cells = [f"{sum(r[2] for r in mine if r[1] == name)}/{options.runs}" for name, _, _ in SCENARIOS]
        total = sum(r[2] for r in mine)
        firsts, totals = sorted(r[3] for r in mine), sorted(r[4] for r in mine)
        print(f"| {variant} | " + " | ".join(cells) + f" | **{total}/{len(mine)}** | "
              f"{firsts[len(firsts) // 2]:.1f} s | {totals[len(totals) // 2]:.1f} s |")
    if options.json:
        with open(options.json, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    main()
