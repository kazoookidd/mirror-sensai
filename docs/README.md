# Sensai — CLI Chatbot (MVP)

A minimal local AI assistant connected to [Ollama](https://ollama.com), built without any LLM
framework (no LangChain, LlamaIndex, etc.) — all calls go directly through the Ollama HTTP API.

## Features (current MVP)

- Functional CLI chatbot connected to a local Ollama model
- **Streaming responses** — output is rendered progressively, not as a single block
- **In-session conversation history** — prior turns are sent as context on every request
- **Clean error handling** — unavailable model, empty input, connection failure, interrupted stream
- **Configurable via `.env`** — model, Ollama URL and system prompt path, no code changes needed
- **CLI overrides** — any `.env` value can be overridden with a command-line flag

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

The system prompt is loaded from a plain text file (`system_prompt.txt` by default) — edit that
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
