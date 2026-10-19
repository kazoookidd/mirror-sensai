# Sensai: CLI Chatbot (MVP)

A minimal local AI assistant connected to [Ollama](https://ollama.com), built without any LLM
framework (no LangChain, LlamaIndex, etc.). All calls go directly through the Ollama HTTP API.

## Features (current MVP)

- Functional CLI chatbot connected to a local Ollama model
- **Streaming responses**: output is rendered progressively, not as a single block
- **In-session conversation history**: prior turns are sent as context on every request
- **Clean error handling**: unavailable model, empty input, connection failure, interrupted stream
- **Configurable via `.env`**: model, Ollama URL and system prompt path, no code changes needed
- **CLI overrides**: any `.env` value can be overridden with a command-line flag
- **RAG over HR documents** ([R1]): answers grounded in your own .txt / .md / .pdf files

## Requirements

- Python 3.10 or higher
- [Ollama](https://ollama.com) installed and running locally

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

Edit `.env` to set your model and options:

```env
MODEL=llama3
OLLAMA_BASE_URL=http://localhost:11434
SYSTEM_PROMPT_PATH=system_prompt.txt
```

Make sure the model is pulled before running:

```bash
ollama pull llama3
```

The system prompt is loaded from a plain text file (`system_prompt.txt` by default). Edit that
file to change the assistant's behavior without touching any code.

## Usage

Start Ollama in the background if it isn't already running:

```bash
ollama serve
```

Then launch the chatbot:

```bash
./start.sh
```

You will be dropped into an interactive session:

```
[System prompt loaded from system_prompt.txt]
Chatbot ready (model: llama3). Type 'exit' to quit.

You: Hello, who are you?
Assistant: I'm Sensai, a helpful assistant...
You: exit
Goodbye.
```

### Overriding config at launch

Any `.env` value can be overridden without editing files:

```bash
./start.sh --model mistral --system-prompt prompts/custom.txt --ollama-url http://localhost:11434
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
| Load | `src/rag/Loader.py` | reads .txt / .md / .pdf files, keeps PDF page numbers |
| Chunk | `src/rag/Chunker.py` | splits text into ~500-token chunks with a 50-token overlap, at paragraph, sentence, line then word boundaries |
| Embed | `src/rag/Embeddings.py` | turns each chunk into a vector with Ollama `/api/embed` (`nomic-embed-text`) |
| Store | `src/rag/Store.py` | saves chunks and vectors in SQLite, re-embeds only new or modified files |
| Retrieve | `src/rag/Retriever.py` | embeds the question, ranks chunks by cosine similarity, keeps the best ones above a threshold, within the token budget |

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
├── chatbot.py          # main script
├── system_prompt.txt   # default system prompt
├── .env.example         # example configuration (copy to .env)
├── requirements.txt     # Python dependencies
├── install.sh           # sets up venv + dependencies + .env
├── start.sh              # activates venv and runs the chatbot
└── README.md
```

## Error handling

| Situation | Behavior |
|---|---|
| Empty input | Prompts the user again, no request sent |
| Ollama not running | Clear error message, session continues |
| Model unavailable / bad request | Clear error message, session continues |
| Connection dropped mid-stream | Error message, that turn is discarded from history |

## Roadmap

This MVP covers the mandatory base loop only. Additional features (memory persistence across
sessions, RAG, guardrails, etc.) are tracked separately as the project scope is defined.
