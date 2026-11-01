"""
[X4] Do the models use ask_form well? (results: docs/benchmarks/forms.md)

ask_form lets the model write a small form of its own. It is off by default
(AGENT_ASK_FORM=false); this benchmark turns it on and runs the real pipeline (HR prompt,
RAG over data/docs, agent, tools) on two kinds of messages:

  * where a form makes sense: the model needs several answers before it can help
  * where it does not: a question it can answer, and a leave request (which has its own form)

Each run says what happened: a form of the model (valid, or refused because its description
was wrong), a one-question ask_user, the leave form, or a plain answer in text. The labels of
the fields are kept, to judge whether they make sense.

Usage (from the project root, Ollama running):
    python back/benchmarks/Bench_forms.py qwen2.5:3b qwen2.5:7b --runs 2
"""

import argparse
import io
import os
import queue
import sys
import tempfile
import time
from contextlib import redirect_stdout
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import Chatbot
from Memories import Database
from Memories.Auth import ROLE_EMPLOYEE, create_user
from Memories.Conversations import create_conversation
from rag import Store
from Web.Output import SseOutput

SHOULD_ASK = [
    "Je veux déclarer un changement d'adresse.",
    "Je voudrais prendre rendez-vous avec le service RH.",
    "Je veux signaler une erreur sur ma fiche de paie.",
]
SHOULD_NOT = [
    "Combien de jours de congé pour un mariage ?",
    "Explique la différence entre un CDD et un CDI en trois phrases.",
    "Je veux poser un congé.",  # the leave form, not a form of the model
]


def outcome(session, events) -> tuple[str, str]:
    """(what happened, detail): model form, refused form, question, leave form or text."""
    card = next((data for name, data in events if name == "confirmation"), None)
    errors = [data["text"] for name, data in events if name == "trace" and data["kind"] == "tool_error"]
    if card and card.get("form"):
        form = card["form"]
        if form["kind"] == "answers":
            fields = ", ".join(f"{f['label']} ({f['kind']})" for f in form["fields"])
            return "model form", f"{card['title']}: {fields}"
        if form["kind"] == "question":
            return "ask_user", card["plan"]
        return "leave form", ""
    if any("ask_form" in error for error in errors):
        return "refused form", errors[-1][:90]
    answer = ""
    for name, data in events:
        if name == "token":
            answer += data["text"]
        elif name == "answer":
            answer = data["text"]
        elif name == "retract" or (name == "trace" and data["kind"] == "thought"):
            answer = ""
    return "text", answer[:90].replace("\n", " ")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("models", nargs="+")
    parser.add_argument("--runs", type=int, default=2)
    options = parser.parse_args()

    tmp = tempfile.TemporaryDirectory()
    patches = [mock.patch.object(Database, "DB_PATH", os.path.join(tmp.name, "forms.db")),
               mock.patch.dict(os.environ, {"AGENT_ASK_FORM": "true"})]
    for patch in patches:
        patch.start()
    Database.init_db()
    create_user("sophie", "sophie@example.com", "password1", role=ROLE_EMPLOYEE)
    with redirect_stdout(io.StringIO()):
        Store.index_directory(Store.DEFAULT_DOCS_DIR)

    rows = []
    for model in options.models:
        with redirect_stdout(io.StringIO()):
            session = Chatbot.build_session(Chatbot.build_parser().parse_args(["--model", model]), "sophie", None)
        session.semantic_cache = False
        for group, messages in (("should ask", SHOULD_ASK), ("should not", SHOULD_NOT)):
            for message in messages:
                for run in range(options.runs):
                    session.conversation_id = create_conversation("sophie", "bench")
                    session.pending_action = None
                    events_queue = queue.Queue()
                    session.out = SseOutput(events_queue)
                    start = time.monotonic()
                    Chatbot.chat_turn(session, message)
                    events = []
                    while not events_queue.empty():
                        events.append(events_queue.get())
                    what, detail = outcome(session, events)
                    rows.append((model, group, message, what, detail, time.monotonic() - start))
                    print(f"{model:12} {group:10} {what:12} {time.monotonic() - start:5.1f}s {message[:45]:45} {detail}",
                          file=sys.stderr)
    for patch in reversed(patches):
        patch.stop()
    tmp.cleanup()

    print("| Model | Message | What happened | Fields proposed, or the start of the answer |")
    print("|---|---|---|---|")
    for model, group, message, what, detail, _ in rows:
        print(f"| {model} | {message} | {what} | {detail.replace('|', '/')} |")
    print()
    for model in options.models:
        mine = [r for r in rows if r[0] == model]
        ask = [r for r in mine if r[1] == "should ask"]
        never = [r for r in mine if r[1] == "should not"]
        print(f"- {model}: form of the model where it made sense {sum(r[3] == 'model form' for r in ask)}/{len(ask)}, "
              f"refused descriptions {sum(r[3] == 'refused form' for r in mine)}, "
              f"form of the model where it did not {sum(r[3] == 'model form' for r in never)}/{len(never)}")


if __name__ == "__main__":
    main()
