# Sensai: local HR assistant (CLI and web)

A local AI assistant connected to [Ollama](https://ollama.com), built without any LLM framework
(no LangChain, LlamaIndex, etc.). All calls go directly through the Ollama HTTP API. The use case
is an HR assistant, centred on employee onboarding.

## Features

- **Streaming responses**: output is rendered progressively, not as a single block
- **Accounts and conversations** ([M1]): login at startup, several independent conversations per user,
  everything stored in SQLite
- **Context compression** ([M2]): old messages are summarised so the context stays under a token
  budget, with metrics
- **Token limit and usage**: block (or continue) past the limit; a small dimmed line shows the tokens
  used by each answer
- **Personas**: switch the assistant's role (onboarding buddy, recruiter, senior HR...) while chatting
- **Runtime switching**: change model, persona, temperature, seed or answer length without restarting
- **Agent with tools** ([A1], ReAct): the model decides by itself when to search the web or read a page,
  with no command needed from the user
- **Semantic cache** ([A6]): a question that means the same as an earlier one is answered instantly, with
  no model call
- **RAG over HR documents** ([R1]): answers grounded in your own .txt / .md / .pdf files
- **Human in the loop** ([A3]): before a critical action the agent suspends and presents its plan; it only
  proceeds after your explicit `/confirm` (or you drop it with `/cancel`). Filing a leave request is the
  critical action: tell Sensai "I take Monday off" in the chat, nothing is written until you confirm
- **Web interface** ([X1]): the same assistant in the browser, streaming answers, live context gauge,
  model switching, settings, history; phone, tablet and desktop, light and dark themes
- **Branches and stop** ([X2]): edit a question or regenerate an answer to continue in a new branch
  (`< 1/2 >` to switch); stop an answer while it is written (Stop button, or Ctrl+C in the CLI)
- **Export and public link** ([X3]): download a chat as Markdown, JSON or PDF (`/export` in the CLI), or
  share a read-only copy through a link that works without logging in and expires after 7 days
- **Configurable via `.env`**, with command-line overrides
- **Clean error handling**: unavailable model, empty input, connection failure, interrupted stream

How it all works, module by module: [docs/Sensai_overview.md](docs/Sensai_overview.md).

## Requirements

- Python 3.10 or higher
- [Ollama](https://ollama.com) installed and running locally
- Node.js 18 or higher, only to build the web interface
- A chat model, and for the RAG and the cache an embedding model:

```bash
ollama pull llama3.1            # or qwen2.5: models that support tool calling
ollama pull nomic-embed-text    # embeddings (RAG and semantic cache)
```

The agent needs a model with **tool calling** (`llama3.1`, `qwen2.5`...). A model without it still
works: it answers without tools, after one dimmed note.

## Installation

```bash
git clone <your-repo-url>
cd sensai
./install.sh
```

`install.sh` will:

1. Check your Python version
2. Create a virtual environment (`.venv`)
3. Install dependencies from `requirements.txt`
4. Build the web interface (`front/dist`), if Node.js is installed
5. Create a `.env` file from `.env.example` (if it doesn't already exist)
6. Pull the embedding model `nomic-embed-text`, if Ollama is installed

With Docker, nothing has to be installed except Docker itself: see [Quick start](#quick-start).

## Quick start

| How | Command | Open |
| --- | --- | --- |
| Terminal (CLI) | `ollama serve`, then `./start.sh` | the terminal |
| Web, local | `ollama serve`, then `./start.sh --web` | http://127.0.0.1:8000 |
| Web, Docker | `docker compose up --build` | http://localhost:3000 |

Accounts are created in the CLI: log in with a new user id and it asks for an email and a password.
The web interface then accepts that user id or that email.

With Docker, Ollama runs in its own container and the first start downloads `qwen2.5:3b` and
`nomic-embed-text` (set `MODEL` in `.env` to use another model). The data lives in Docker volumes, apart
from the local `storage/sensai.db`, so create the account inside the container:

```bash
docker compose up --build -d                 # front on :3000, API on :8080
docker compose exec back python back/Chatbot.py   # log in once to create the account, then type exit
docker compose logs -f back                  # server logs
docker compose down                          # stop (add -v to also delete the volumes)
```

## Configuration

Edit `.env`. Every variable has a default in the code, so a short file is enough:

```env
MODEL=llama3.1
OLLAMA_BASE_URL=http://localhost:11434
SYSTEM_PROMPT_PATH=back/config/system_prompt.txt
```

| Group | Variables |
| --- | --- |
| Model and prompt | `MODEL`, `OLLAMA_BASE_URL`, `SYSTEM_PROMPT_PATH`, `PERSONAS_DIR`, `DEFAULT_PERSONA` |
| Answers | `TEMPERATURE`, `SEED`, `NUM_PREDICT` (unset = the model's default) |
| Context ([M2]) | `CONTEXT_TOKEN_BUDGET` (4000), `CONTEXT_THRESHOLD_RATIO` (0.8), `CONTEXT_KEEP_LAST_N` (10) |
| Token limit | `TOKEN_LIMIT_ACTION` (`block` or `continue`), `SHOW_TOKEN_USAGE` |
| Agent ([A1]) | `AGENT_TOOLS`, `AGENT_MAX_STEPS` (4), `AGENT_TEMPERATURE`, `AGENT_SHOW_ACTIVITY`, `AGENT_TOOLS_PATH` |
| Web search | `BRAVE_SEARCH_API_KEY`, `TAVILY_API_KEY`, `EXA_API_KEY` (only the engine you use) |
| Cache ([A6]) | `CACHE_ENABLED`, `CACHE_EMBED_MODEL`, `CACHE_SIMILARITY` (0.92), `CACHE_TTL_HOURS` (168), `CACHE_MAX_ENTRIES` (500), `CACHE_SCOPE` (`user`), `CACHE_CONTEXT_FREE_ONLY` |
| RAG ([R1]) | see the RAG section below |

The system prompt is loaded from a plain text file (`back/config/system_prompt.txt` by default). Personas
are one JSON file each in `back/config/personas/` (`name`, `description`, `system_prompt`).

## Usage

Start Ollama in the background if it isn't already running:

```bash
ollama serve
```

Then launch the chatbot:

```bash
./start.sh
```

You log in (a new user id creates an account), pick or start a conversation, then chat:

```
=== Login ===
User ID: alice
...
Chatbot ready (model: llama3.1, persona: Sensai (default), temperature: model default).
Type /help for the commands, 'exit' to quit.

You: Comment poser un jour de congé payé ?
Assistant: Rendez-vous dans le portail RH, rubrique congés...
tokens: 27 in · 21 out
```

### Overriding config at launch

```bash
./start.sh --model qwen2.5:3b --persona hr_senior --temperature 0.3 --on-token-limit continue
```

### Commands

| Command | Effect |
| --- | --- |
| `/help` | show the commands |
| `/new`, `/conversations` | start a new conversation, or switch to an existing one |
| `/personas`, `/persona [id\|number]` | list the personas, switch persona (history is kept) |
| `/models`, `/model [name\|number]` | list the models installed in Ollama, switch model |
| `/temperature [value\|default]` | show or set how creative the answers are (0 to 2) |
| `/settings [name [value]]` (`/set`) | list the settings or change one: `temperature`, `token-limit`, `token-usage`, `cache`, `seed`, `num-predict` |
| `/search`, `/switch_search [name\|number]` | list / switch the search engine (Brave, Tavily, Exa) |
| `/confirm`, `/cancel` | go ahead with the action waiting for your approval, or drop it |
| `/leaves` | list the leave requests you filed |
| `/ingest [folder]` | index HR documents for the RAG (also empties the semantic cache) |
| `/cache [clear]` | show the semantic cache, or empty it |
| `/export [md\|json\|pdf]` | save the conversation to a file in `exports/` (default: Markdown) |
| `exit` | quit |

## Agent and tools ([A1])

The user never asks for tools: the model decides. When it wants one, Ollama returns a structured
`tool_calls` field, the program runs the tool and gives the result back, until the model answers.
A message that needs no tool costs **one** model call.

```
You: Qui est le PDG de Renault ?
  · Searching the web: PDG Renault
Assistant: D'après les résultats trouvés (https://...), ...
```

- Tools are declared in `back/Tools/tools.json` (`search_internet`, `read_webpage`).
- Greetings and thanks are answered without offering tools.
- Guards for small models: a limit of steps, an identical call is not run twice, a bad tool call is
  reported to the model instead of crashing, and an answer that repeats an old one is rejected.
- Adding a tool: one entry in `tools.json` + one provider in `back/Agents/Setup.py`.

### Human in the loop ([A3])

A tool marked `"critical": true` in `tools.json` can never act on its own. `file_leave_request` is the first
one: when the user says "je pose lundi", the agent fills the fields itself, **suspends** (no further model
call) and presents its plan:

```
You: Je pose du 3 au 7 novembre pour des vacances
  · Preparing a leave request: paid_leave, 2026-11-03, 2026-11-07, vacances
Assistant: === Leave request to confirm ===
I will file this leave request for alice:
  type:   paid_leave
  from:   2026-11-03
  to:     2026-11-07
  reason: vacances
Nothing has been done yet. Type /confirm to go ahead, or /cancel to drop it.
You: /confirm
Leave request #7 saved for alice. See all yours with /leaves.
```

- The action only runs on `/confirm`, with exactly the data that was shown. `/cancel`, or a new request, drops it.
- The pending action is held on the server, in the user's session: the same in the terminal and in the web UI.
- In the web UI the plan is shown as a card with **Confirm** and **Cancel** (they run `/confirm` and `/cancel`).
  The card stays after a page reload, and disappears once nothing is waiting any more.
- Safety nets: the registry refuses to run a critical tool directly, and a critical tool that does not return
  an action to confirm is treated as an error (it fails closed).
- Never cached by the semantic cache (tools were used).

## Semantic cache ([A6])

A question that means the same as an earlier one gets the stored answer, with no model call:

```
You: comment poser un jour de congé payé ?
Assistant: Rendez-vous dans le portail RH, rubrique congés...
  · answered from the cache (96% similar to an earlier question, no model call)
```

It is cautious on purpose, because a wrong cached answer is worse than a slow one:

- never served for a follow-up ("and tomorrow?") or a time-sensitive question ("today", "latest", "what day")
- never stored if tools were used, if the answer is a refusal, or if a real conversation came before
- per user by default (`CACHE_SCOPE=user`): employees do not share answers
- answers expire after 168 hours; `/ingest` empties the cache; `/cache clear` and `/settings cache off`
  are available at any time

It needs the embedding model (`ollama pull nomic-embed-text`). If it is missing, one note is shown and the
cache is turned off for the session.

## Web interface ([X1])

```bash
./start.sh --web          # then open http://127.0.0.1:8000
./start.sh --web --port 8080 --model qwen2.5:3b
```

The interface is built by `install.sh` (it needs Node.js 18+). To build it by hand, or to work on it with
hot reload:

```bash
cd front && npm install && npm run build   # front/dist, served by ./start.sh --web
npm run dev                                # http://localhost:5173, API calls sent to 127.0.0.1:8000
```

The web interface is a front end over the same backend as the CLI: the server (`back/Server.py`,
`back/Web/`) calls `chat_turn`, the accounts, the conversations and the settings exactly as the terminal
does. Only the output differs: the chat turn writes to `session.out` (`back/Runtime/Output.py`), which is
the terminal for the CLI and a stream of Server-Sent Events for the browser.

- Log in with an account created in the CLI (its email or its user id).
- Answers stream word by word; the gauge under the composer shows the context used against
  `CONTEXT_TOKEN_BUDGET`.
- Model, persona, temperature and answer length are changed live, with the same checks as `/model`,
  `/persona` and `/settings` (persona: sidebar and Settings; the chat history is kept).
- History: search, sort, rename, delete (also from the "⋯" menu of each recent chat in the sidebar).
  Documents: the files of `data/docs`, whether they are indexed, and importing new ones (see the RAG section).
- Typing `/` in the composer lists the slash commands with what they do; they run on the same code as
  the CLI (`POST /api/command`), and the output is shown in the chat without being saved.
- Desktop: a left sidebar (sections, recent chats, model, Ollama status). Clicking the account opens a
  menu (Profile, Settings, Log out); Profile and Settings open in a tabbed window over the current page.
  Phones and tablets: a tab bar, with a swipe between Chat, Documents and History, and Settings and
  Profile as full pages.
- Export and Share above the chat (in the app bar on phones and tablets): download the chat shown as
  Markdown, JSON or PDF, or create a public link (`#/share/<token>`). The link opens without logging in,
  read only, and shows a copy of the chat as it was when it was shared; it expires after 7 days, and
  "Stop sharing" or deleting the chat turns it off at once. It never shows who shared it. The server only
  listens on this machine by default, so the link opens on this machine (or your network, if you set
  `WEB_HOST`).
- Light, dark or system theme.
- The server listens on `127.0.0.1` only (`WEB_HOST`, `WEB_PORT` in `.env`).

Controls marked `[TEST]` are designed but not connected yet: querying a selection of documents, the menu of
each document, sources under the answers, the documents toggle, the profile page, and the model used
by each past conversation.

The front end (`front/`) is React 18 with Vite, in JavaScript (JSX). Each component has its CSS Module
next to it; only the design tokens, fonts and a few utilities are global (`src/styles/`):

```
front/src/
├── main.jsx, App.jsx    # entry point, routes (#/chat, #/documents, #/history, #/settings, #/profile, #/share), error screen
├── context/             # AppContext: user, Ollama status, models, context gauge, recent chats
├── api/                 # every call to the backend: HTTP and streaming helpers, one file per domain
├── lib/                 # shared helpers: formats, theme, safe Markdown rendering
├── components/          # shared components: ui/ (Button, Field, Dialog...) and feedback/ (EmptyState...)
├── layout/              # AppShell, left sidebar, mobile app bar and tab bar, Page, slide transitions
└── features/            # one folder per domain, with its pages and components:
                         # auth, chat, export, ollama, personas, history, documents, settings, profile, account, errors
```

Front tests (Vitest, no server or Ollama needed) sit next to the file they test:

```bash
cd front && npm test
```

## RAG: answers from your HR documents

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
Indexing .../data/docs... (can take a minute the first time)
8 document(s) indexed (69 chunks), 0 unchanged, 0 removed.
```

Run `/ingest` again after adding, editing or deleting documents: only changed files are
processed again, and deleted files are removed from the index.

In the web interface, **Documents > Import a document** (or a drop on the dashed zone) saves `.txt`, `.md` or
`.pdf` files of up to 10 MB in `data/docs` and runs the same indexing as `/ingest`, on this machine. A file
with no readable text (a scanned PDF) is refused; if Ollama does not answer, the file is kept and indexed by
the next import or `/ingest`. Any logged-in user can import: the base is shared by every account. Under
Docker, `data/docs` is the `sensai_docs` volume, so imported files survive a rebuild.

**Files joined to one chat**: the paperclip of the composer joins `.txt`, `.md` or `.pdf` files (10 MB at most)
to the current chat only. They go through the same pipeline but are stored apart (`rag/Attachments.py`):
nobody else sees them, they never enter the shared base, the branches of the chat keep them, and deleting
the chat deletes them. At each question, their passages are ranked by similarity and added, without the
score threshold of the base, until 60 % of the free context is used, then given in file order: a small file
goes in whole (so "summarize the attached file" works), a big one gives its closest passages. A chat with
joined files never uses the semantic cache, and a question about "the file" or "ce document" is answered
without tools, since the text is already in the context.

### Asking questions

Just ask. The most relevant excerpts are added to the model's context for that question only:

```
You: Combien de jours de congé pour un mariage ?
Assistant: Le salarié peut bénéficier d'un congé de 4 jours pour un mariage...
```

A question unrelated to the documents ("Quelle est la recette de la pizza ?") gets no excerpt.

### How it works


| Step     | File                    | What it does                                                                                                           |
| -------- | ----------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Load     | `back/rag/Loader.py`     | reads .txt / .md / .pdf files, keeps PDF page numbers                                                                  |
| Chunk    | `back/rag/Chunker.py`    | splits text into ~500-token chunks with a 50-token overlap, at paragraph, sentence, line then word boundaries          |
| Embed    | `back/rag/Embeddings.py` | turns each chunk into a vector with Ollama`/api/embed` (`nomic-embed-text`)                                            |
| Store    | `back/rag/Store.py`      | saves chunks and vectors in SQLite, re-embeds only new or modified files                                               |
| Retrieve | `back/rag/Retriever.py`  | embeds the question, ranks chunks by cosine similarity, keeps the best ones above a threshold, within the token budget |

### Settings (`.env`)


| Variable            | Default            | Meaning                                               |
| ------------------- | ------------------ | ----------------------------------------------------- |
| `RAG_EMBED_MODEL`   | `nomic-embed-text` | Ollama model used for embeddings                      |
| `RAG_CHUNK_TOKENS`  | `500`              | chunk size, in estimated tokens                       |
| `RAG_CHUNK_OVERLAP` | `50`               | overlap between two chunks, in estimated tokens       |
| `RAG_MIN_SCORE`     | `0.70`             | minimum similarity (0 to 1) for an excerpt to be used |
| `RAG_TOP_K`         | `3`                | maximum number of excerpts per question               |

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
│   ├── Chatbot.py            # startup, login, Ollama call, chat loop
│   ├── Server.py             # web interface entry point (./start.sh --web)
│   ├── Web/                  # FastAPI app, sessions, SSE output, one route file per domain
│   ├── Commands.py           # Session state and the slash commands
│   ├── Memories/             # SQLite: users, conversations, history, compression, token limit
│   ├── Runtime/              # personas, models, settings and parameters
│   ├── Agents/               # ReAct loop, tool registry, router, engine, tool providers
│   ├── Tools/                # tools.json, web search, page reader
│   ├── Cache/                # semantic cache: storage, policy, chat glue
│   ├── Export/               # [X3] JSON / Markdown / PDF export (fpdf2, Noto Sans font) and public links
│   ├── rag/                  # loader, chunker, embeddings, store, retriever
│   ├── config/               # system_prompt.txt and personas/ (one JSON file per persona)
│   ├── tests/                # Test_*.py (no real Ollama needed)
│   └── Dockerfile            # image of the API server (docker compose)
├── front/                    # web interface: React + Vite (src/), icons and fonts (public/), Dockerfile + nginx.conf
├── data/docs/                # HR documents for the RAG
├── storage/                  # sensai.db (accounts, conversations, RAG index, cache), not in git
├── docs/                     # user stories (docs/user_stories/) and the HR scenario
├── .env.example              # example configuration (copy to .env)
├── requirements.txt          # Python dependencies
├── install.sh                # sets up venv + dependencies + web build + .env
├── start.sh                  # activates venv and runs the chatbot (--web: web interface)
├── docker-compose.yml        # front + API + Ollama in containers (http://localhost:3000)
└── README.md
```

## Tests

No real Ollama is needed: a small local server plays the part of `/api/chat` and `/api/embed`, and the
database is a temporary file. From the project root:

```bash
source .venv/bin/activate
python -m unittest discover -s back/tests -p "Test_*.py"
```

## Error handling

| Situation | Behavior |
| --- | --- |
| Empty input | Prompts the user again, no request sent |
| Ollama not running | Clear error message, session continues |
| Model unavailable / bad request | Clear error message, session continues |
| Connection dropped mid-stream | Error message, that turn is not saved |
| Context over the token limit | Message refused with the way out (`/new`), or sent with a warning (`TOKEN_LIMIT_ACTION=continue`) |
| Model without tool calling | Answers without tools, one dimmed note |
| A tool fails | The error goes back to the model, which can correct itself |
| Embedding model missing | Semantic cache turned off for the session, one note |

## Known limits

- Everything was tested against a fake Ollama: the real behaviour depends on the model.
- Tools and their instructions add about 600 tokens to a message when they are offered.
- Very small models can still get dates wrong or ignore a search result.
- The persona is not stored per conversation; the persistent profile ([M1]) is not done yet.

## Roadmap

Planned or open: guardrails, a persistent user profile, more tools for the agent, and the `[TEST]` controls of the web interface.
