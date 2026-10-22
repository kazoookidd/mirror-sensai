# Sensai: local HR assistant (CLI)

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
- **Structured output** ([T5]): `/leave` turns a plain-language request into a validated leave request
- **Configurable via `.env`**, with command-line overrides
- **Clean error handling**: unavailable model, empty input, connection failure, interrupted stream

How it all works, module by module: [docs/Sensai_overview.md](docs/Sensai_overview.md).

## Requirements

- Python 3.10 or higher
- [Ollama](https://ollama.com) installed and running locally
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
4. Create a `.env` file from `.env.example` (if it doesn't already exist)

## Configuration

Edit `.env`. Every variable has a default in the code, so a short file is enough:

```env
MODEL=llama3.1
OLLAMA_BASE_URL=http://localhost:11434
SYSTEM_PROMPT_PATH=system_prompt.txt
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

The system prompt is loaded from a plain text file (`system_prompt.txt` by default). Personas are one
JSON file each in `personas/` (`name`, `description`, `system_prompt`).

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
| `/leave <request>`, `/leaves` | file a leave request in plain language, list yours |
| `/ingest [folder]` | index HR documents for the RAG (also empties the semantic cache) |
| `/cache [clear]` | show the semantic cache, or empty it |
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

- Tools are declared in `src/Tools/tools.json` (`search_internet`, `read_webpage`).
- Greetings and thanks are answered without offering tools.
- Guards for small models: a limit of steps, an identical call is not run twice, a bad tool call is
  reported to the model instead of crashing, and an answer that repeats an old one is rejected.
- Adding a tool: one entry in `tools.json` + one provider in `src/Agents/Setup.py`.

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
| Load     | `src/rag/Loader.py`     | reads .txt / .md / .pdf files, keeps PDF page numbers                                                                  |
| Chunk    | `src/rag/Chunker.py`    | splits text into ~500-token chunks with a 50-token overlap, at paragraph, sentence, line then word boundaries          |
| Embed    | `src/rag/Embeddings.py` | turns each chunk into a vector with Ollama`/api/embed` (`nomic-embed-text`)                                            |
| Store    | `src/rag/Store.py`      | saves chunks and vectors in SQLite, re-embeds only new or modified files                                               |
| Retrieve | `src/rag/Retriever.py`  | embeds the question, ranks chunks by cosine similarity, keeps the best ones above a threshold, within the token budget |

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
├── src/
│   ├── Chatbot.py            # startup, login, Ollama call, chat loop
│   ├── Commands.py           # Session state and the slash commands
│   ├── leave_request.py      # structured leave request from the command line
│   ├── Memories/             # SQLite: users, conversations, history, compression, token limit
│   ├── Runtime/              # personas, models, settings and parameters
│   ├── Agents/               # ReAct loop, tool registry, router, engine, tool providers
│   ├── Tools/                # tools.json, web search, page reader
│   ├── Cache/                # semantic cache: storage, policy, chat glue
│   ├── rag/                  # loader, chunker, embeddings, store, retriever
│   ├── StructuredOutput/     # leave request extraction and storage
│   └── tests/                # Test_*.py (no real Ollama needed)
├── personas/                 # one JSON file per persona
├── data/docs/                # HR documents for the RAG
├── docs/                     # user stories and docs/Sensai_overview.md
├── system_prompt.txt         # default system prompt
├── .env.example              # example configuration (copy to .env)
├── requirements.txt          # Python dependencies
├── install.sh                # sets up venv + dependencies + .env
├── start.sh                  # activates venv and runs the chatbot
└── README.md
```

## Tests

No real Ollama is needed: a small local server plays the part of `/api/chat` and `/api/embed`, and the
database is a temporary file. From the project root:

```bash
python src/tests/Test_runtime.py
python src/tests/Test_tokens.py
python src/tests/Test_react.py
python src/tests/Test_engine.py
python src/tests/Test_cache.py
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

Planned or open: guardrails, a web interface ([X1]), a persistent user profile, more tools for the agent.
