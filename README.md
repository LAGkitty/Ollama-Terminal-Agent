# 🤖 Ollama Terminal Agent

An autonomous terminal agent that uses locally running [Ollama](https://ollama.com) models to complete multi-step shell tasks. Give it a goal in plain English — it figures out the commands, runs them, reads the output, self-corrects on errors, and keeps going until the task is genuinely done.

```
  ╔══════════════════════════════════════════╗
  ║    🤖   O L L A M A   A G E N T         ║
  ╚══════════════════════════════════════════╝

  ● Ollama: running   1 model(s)

  Main Menu
  ──────────────────────────────────────────
  1. ▶  Run Task         auto-select model
  2. ⚙  Run Task         choose model manually
  3. ↓  Pull a Model
  4. ✓  System Check
  5. ⟳  Start Ollama     if stopped
  0. Exit
```

---

## Features

- **Interactive launcher** — clean terminal menu to start tasks, pick models, pull new ones, or run a system check
- **Live streaming output** — every command's output prints line-by-line in real time, no waiting
- **Self-correcting loop** — if a command fails, the agent reads the error and tries a different approach automatically
- **Thinking spinner** — shows which step the agent is on while it's processing
- **JSON retry system** — if the model produces malformed output, it re-prompts up to 5 times before giving up
- **Auto endpoint detection** — works with both `/api/chat` (newer Ollama) and `/api/generate` (older) automatically
- **Auto model selection** — picks the best available model, or let you choose manually
- **Auto-starts Ollama** — if the service isn't running, it starts it for you
- **Works with any model** — compatible with any Ollama model that can follow instructions

---

## Requirements

- Python 3.8+
- [Ollama](https://ollama.com/download) installed
- `requests` Python library

```bash
pip install requests
```

---

## Installation

```bash
# Clone or download
git clone https://github.com/yourname/ollama-terminal.git
cd ollama-terminal

# Install dependency
pip install requests

# Pull a model (if you don't have one yet)
ollama pull llama3

# Run
python ollama_terminal.py
```

---

## Usage

### Interactive menu (recommended)
```bash
python ollama_terminal.py
```

### Run a task directly from the command line
```bash
python ollama_terminal.py "create a python script that counts words in a file"
python ollama_terminal.py -m mistral "check for flatpak updates"
```

### System check
```bash
python ollama_terminal.py --check
```

---

## Recommended Models

All models are pulled with `ollama pull <name>` or from the Pull menu inside the app.

| Model | Size | Best for |
|---|---|---|
| `llama3:latest` | 4.7 GB | Best all-rounder, great JSON discipline ⭐ |
| `llama3.1:latest` | 4.9 GB | Better multi-step reasoning ⭐ |
| `mistral:latest` | 4.1 GB | Fast, reliable, stays on task ⭐ |
| `qwen2.5-coder` | 4.7 GB | Coding and dev tasks ⭐ |
| `deepseek-r1` | 4.7 GB | Complex reasoning, thorough ⭐ |
| `gemma2:2b` | 1.6 GB | Lightweight, good for simple tasks |
| `phi3:mini` | 2.2 GB | Very fast, occasional JSON issues |
| `llama2` | 3.8 GB | Older, less reliable for agentic use |
| Models under ~1B params | — | ⚠️ Too small, unreliable JSON output |

> **Tip:** For agentic tasks (running commands, fixing errors, multi-step work) `llama3.1` or `mistral` give the best balance of speed and reliability.

---

## How it works

1. You describe a task in plain English
2. The agent sends it to your local Ollama model with a strict system prompt requiring JSON-only responses
3. The model replies with `{"action": "run", "command": "...", "reason": "..."}`
4. The agent runs the command and streams all output live
5. The full output (stdout + stderr + exit code) is fed back to the model
6. The model decides: fix an error, run the next command, ask you a question, or declare done
7. This loops until the model sends `{"action": "done", "summary": "..."}` — meaning it has **verified** the task is complete

Everything runs **100% locally** — no API keys, no cloud, no data sent anywhere.

---

## Example tasks

```
check flatpak updates
create a folder called projects with a README.md inside
find all .log files older than 7 days and delete them
install the requests python library and verify it works
show me disk usage sorted by size
git clone https://github.com/user/repo and set it up
```

---

## Configuration

Edit the constants at the top of `ollama_terminal.py`:

```python
OLLAMA_BASE      = "http://localhost:11434"  # Ollama server address
MAX_ITERATIONS   = 60    # Max steps before giving up
MAX_JSON_RETRIES = 5     # Retries on bad model output
```

---

## Troubleshooting

**`Cannot connect to Ollama`**
Run `ollama serve` in a separate terminal, or use menu option 5.

**Model keeps producing bad JSON**
Try a larger or more capable model. Models under ~3B parameters often struggle with strict JSON formatting.

**Command times out**
The default timeout per command is 120 seconds. Increase it in `run_cmd()` if you're running long installs.

**Task loops without finishing**
The model may be confused by ambiguous output. Try rephrasing your task more specifically.

---

## License

MIT
