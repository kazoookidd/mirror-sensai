# Sensai: local HR assistant

Sensai is an internal HR assistant that runs entirely on your machine with
[Ollama](https://ollama.com). Employees ask about their rights (leave, remote work, salary
agreements) and get answers taken from the company's own HR documents.

It is built without any LLM framework (no LangChain, LlamaIndex, etc.): every model call goes
directly through the Ollama HTTP API. The use case is described in
[`docs/Scenario.md`](Scenario.md).

## Features

| Code | Feature | How to use it |
|---|---|---|
| B1 | CLI chatbot with streaming answers and clean error handling | `./start.sh` |
| M1 | Accounts, persistent history, several conversations per user | login at startup, `/new`, `/conversations` |
| M2 | Context compression and token limit, token usage under each answer | automatic, `/settings` |
| R1 | RAG: answers based on your HR documents | `/ingest`, then ask a question |
| A5 | HR personas, model switching at runtime | `/personas`, `/persona`, `/models`, `/model` |
| A1 + T3 | ReAct agent: the model searches the web when it needs to | automatic (`AGENT_TOOLS=true`) |
| A3 | Human in the loop: the agent presents its plan and waits | `/confirm`, `/cancel`, `/leaves` |
| | Temperature setting | `/temperature` |
| X1 | Web interface: streaming chat, context gauge, model and settings, history, documents | `./start.sh --web` |

User stories for each feature are in [`docs/user_stories/`](user_stories/).

## Requirements

- Python 3.10 or higher
- [Ollama](https://ollama.com) installed and running (`ollama serve`)
- A chat model with tool support, e.g. `ollama pull qwen2.5:3b`
- For web search only: an API key for Brave, Tavily or Exa

## Installation

```bash
git clone <your-repo-url>
cd sensai
./install.sh
```

`install.sh` checks your Python version, creates a virtual environment (`.venv`), installs
`requirements.txt`, builds the web interface (if Node.js is installed), creates `.env` from
`.env.example` and pulls the embedding model `nomic-embed-text` used by the RAG.

## Configuration

Everything is set in `.env` (see `.env.example` for every option). The main ones:

| Variable | Default | Meaning |
|---|---|---|
| `MODEL` | `llama3` | chat model, it must be pulled in Ollama first |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `TEMPERATURE` | empty (model default) | 0 (precise) to 2 (creative) |
| `CONTEXT_TOKEN_BUDGET` | `4000` | token budget of the context |
| `TOKEN_LIMIT_ACTION` | `block` | `block` or `continue` when the context is over the budget |
| `AGENT_TOOLS` | `true` | let the model use its tools (web search) |
| `BRAVE_SEARCH_API_KEY`, `TAVILY_API_KEY`, `EXA_API_KEY` | | keys of the search engines |

Most of them can also be given at launch, for example:

```bash
./start.sh --model qwen2.5:3b --persona hr_onboarding --temperature 0.2
```

Run `./start.sh --help` to see every option.

## Usage

```bash
ollama serve          # in another terminal, if Ollama is not running
./start.sh
```

At startup, log in (an account is created the first time), then pick a conversation or start
a new one.

```
You: /ingest
8 document(s) indexed (69 chunks), 0 unchanged, 0 removed.
You: Combien de jours de congé pour un mariage ?
Assistant: Le salarié peut bénéficier d'un congé de 4 jours pour un mariage.
You: exit
Goodbye.
```

### Commands

| Command | What it does |
|---|---|
| `/help` | list the commands |
| `/new`, `/conversations` | start a new conversation, or switch to another one |
| `/personas`, `/persona [id]` | list the personas, or switch to one |
| `/models`, `/model [name]` | list the installed models, or switch to one |
| `/temperature [value]` | show or set the temperature |
| `/settings [name [value]]` | show or change a setting |
| `/search`, `/switch_search [name]` | list the search engines, or switch to one |
| `/confirm`, `/cancel` | go ahead with the action waiting for your approval, or drop it |
| `/leaves` | list the leave requests you filed |
| `/ingest [folder]` | index HR documents for the RAG (default: `data/docs`) |
| `exit` | quit |

Switching persona, model or any setting keeps the conversation history.

## RAG: answers from your HR documents [R1]

The assistant can answer from your own documents (HR policies, agreements, legal fact sheets).
Everything runs locally: embeddings are computed by Ollama and stored in the SQLite database.

### Setup

Pull the embedding model once:

```bash
ollama pull nomic-embed-text
```

Then, in the chatbot, index the documents of `data/docs` (or any folder):

```
You: /ingest
Indexing .../data/docs...
8 document(s) indexed (69 chunks), 0 unchanged, 0 removed.
```

Run `/ingest` again after adding, editing or deleting documents: only changed files are
processed again, and deleted files are removed from the index.

### Asking questions

Just ask. The most relevant excerpts are added to the model's context for that question only:

```
You: Combien de jours de congé pour un mariage ?
Assistant: Le salarié peut bénéficier d'un congé de 4 jours pour un mariage...
```

A question unrelated to the documents ("Quelle est la recette de la pizza ?") gets no excerpt.

### How it works

| Step | File | What it does |
|---|---|---|
| Load | `back/rag/Loader.py` | reads .txt / .md / .pdf files, keeps PDF page numbers |
| Chunk | `back/rag/Chunker.py` | splits text into ~500-token chunks with a 50-token overlap, at paragraph, sentence, line then word boundaries |
| Embed | `back/rag/Embeddings.py` | turns each chunk into a vector with Ollama `/api/embed` (`nomic-embed-text`) |
| Store | `back/rag/Store.py` | saves chunks and vectors in SQLite, re-embeds only new or modified files |
| Retrieve | `back/rag/Retriever.py` | embeds the question, ranks chunks by cosine similarity, keeps the best ones above a threshold, within the token budget |

### Settings (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `RAG_EMBED_MODEL` | `nomic-embed-text` | Ollama model used for embeddings |
| `RAG_CHUNK_TOKENS` | `500` | chunk size, in estimated tokens |
| `RAG_CHUNK_OVERLAP` | `50` | overlap between two chunks, in estimated tokens |
| `RAG_MIN_SCORE` | `0.70` | minimum similarity (0 to 1) for an excerpt to be used |
| `RAG_TOP_K` | `3` | maximum number of excerpts per question |

Changing `RAG_EMBED_MODEL` or the chunk settings requires running `/ingest` again.

### Limits

- Scanned PDFs (images without text) are skipped: there is no OCR.
- The 0.70 threshold was measured on the demo documents. With other documents or another
  embedding model, measure it again.
- Small chat models do not always cite the source of the excerpts in their answer.

## Project structure

```
sensai/
├── back/
│   ├── Chatbot.py          # startup, login and chat loop
│   ├── Server.py           # web interface entry point (X1)
│   ├── Web/                # FastAPI app, sessions, SSE output, API routes
│   ├── Commands.py         # session state and slash commands
│   ├── Memories/           # SQLite database, accounts, history, compression, token limit
│   ├── rag/                # RAG: loader, chunker, embeddings, store, retriever
│   ├── Agents/             # ReAct loop and tool handling
│   ├── Tools/              # web search tools and their declarations
│   ├── Runtime/            # personas, models, temperature, settings
│   ├── config/             # system_prompt.txt and personas/ (JSON)
│   └── tests/              # unit tests
├── front/                  # web interface: React + Vite, CSS Modules, icons, fonts
├── data/docs/              # HR documents indexed by /ingest
├── storage/                # sensai.db (not in git)
├── docs/                   # README, scenario, user_stories/
├── .env.example            # configuration template (copy to .env)
├── requirements.txt
├── install.sh
└── start.sh
```

## Tests

```bash
source .venv/bin/activate
python3 -m unittest discover -s back/tests -p "Test_*.py"
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `cannot connect to Ollama` | start it with `ollama serve` |
| `model ... not found` | pull it: `ollama pull <model>`, or pick an installed one with `/model` |
| `no such column: conversation_id` at startup | your database was created by an older version: delete `storage/sensai.db`, then log in and run `/ingest` again |
| The answers ignore the HR documents | run `/ingest`, and ask full questions rather than keywords |
