# 🤖 Ollama Terminal

An autonomous terminal agent that uses locally running [Ollama](https://ollama.com) models to complete multi-step shell tasks. Describe a goal in plain English — it figures out the commands, runs them, reads the output, self-corrects on errors, and keeps going until the task is genuinely done. Everything runs **100% locally** — no API keys, no cloud, no data sent anywhere.

---

## Demo

```
  ╔══════════════════════════════════════════╗
  ║    🤖   O L L A M A   T E R M I N A L   ║
  ╚══════════════════════════════════════════╝

  ● Ollama: running   2 model(s)  [custom instructions]

  Main Menu
  ──────────────────────────────────────────────────────────
  1. ▶  Run Task              auto-select model
  2. ⚙  Run Task              choose model manually
  3. ⭐  Saved Tasks           (2 saved)
  4. ↓  Pull a Model
  5. ✓  System Check
  6. ✏  Custom Instructions   add rules / context
  7. ⟳  Start Ollama          if stopped
  0. Exit
  ──────────────────────────────────────────────────────────
  Choice: 1

  Auto-selected: llama3:latest

  What do you want me to do?
  > set up a python project called weather-cli with a venv, install requests, and write a hello world script

  Connected (chat)

  ──────────────────────────────────────────────────────────
  Model: llama3:latest
  Task:  set up a python project called weather-cli with a venv, install requests, and write a hello world script
  ──────────────────────────────────────────────────────────

  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  Step 1  explore home directory
  ┌─ $ ls /home/alex
  │ Desktop  Documents  Downloads  Music  Pictures
  └─ ✓

  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  Step 2  create project folder
  ┌─ $ mkdir -p /home/alex/Documents/weather-cli
  └─ ✓

  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  Step 3  create virtual environment
  ┌─ $ python3 -m venv /home/alex/Documents/weather-cli/venv
  └─ ✓

  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  Step 4  install requests into venv
  ┌─ $ /home/alex/Documents/weather-cli/venv/bin/pip install requests
  │ Collecting requests
  │   Downloading requests-2.32.3-py3-none-any.whl (64 kB)
  │ Installing collected packages: requests
  │ Successfully installed requests-2.32.3
  └─ ✓

  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  Step 5  write hello world script

  ❓ Agent asks: Should the script print to stdout or write to a log file?
     Your answer: stdout is fine

  ┌─ $ printf 'print("Hello from weather-cli!")\n' > /home/alex/Documents/weather-cli/main.py
  └─ ✓

  ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  Step 6  verify script runs correctly
  ┌─ $ /home/alex/Documents/weather-cli/venv/bin/python main.py
  │ Hello from weather-cli!
  └─ ✓

  ══════════════════════════════════════════════════════════
  ✓  Task complete!

  Created weather-cli project with venv, installed requests,
  wrote and verified main.py — all in /home/alex/Documents/weather-cli
  ══════════════════════════════════════════════════════════

  Save as a saved task? [y/N]: y
  ✓ Saved!

  Press Enter to return to menu…
```

---

## Features

- **Interactive launcher** — clean terminal menu to run tasks, pick models, pull new ones, or check system status
- **Auto-detects system info** — reads your username, home directory, OS, and shell automatically so paths are always correct
- **Live streaming output** — every command's output prints line-by-line in real time as it runs
- **Self-correcting loop** — on failure the agent reads the error and tries a different approach, never repeating a broken command
- **Thinking spinner** — animated indicator shows which step the agent is on while it processes
- **JSON retry system** — if the model produces malformed output it re-prompts up to 5 times before doing a hard reset
- **Context trimming** — conversation history is capped to prevent the model from getting confused on long tasks
- **Custom Instructions** — add persistent rules, preferences, or context that apply to every run (saved to `~/.ollama_terminal_config.json`)
- **Saved Tasks** — save frequently used tasks and re-run them with one keypress
- **Auto endpoint detection** — works with both `/api/chat` (newer Ollama) and `/api/generate` (older) automatically
- **Auto model selection** — picks the best available model, or choose manually
- **Auto-starts Ollama** — if the service isn't running, it starts it for you
- **Works with any Ollama model** — compatible with any model that can follow structured instructions

---

## Requirements

- Python 3.8+
- [Ollama](https://ollama.com/download) installed and running
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

# Pull a model
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

### Run a task directly
```bash
python ollama_terminal.py "find all .log files older than 7 days and delete them"
python ollama_terminal.py -m mistral "check for flatpak updates"
```

### System check
```bash
python ollama_terminal.py --check
```

---

## Recommended Models

Pull any model with `ollama pull <name>` or use option 4 in the menu.

| Model | Size | Best for |
|---|---|---|
| `llama3:latest` | 4.7 GB | ⭐ Great all-rounder |
| `llama3.1:latest` | 4.9 GB | ⭐ Better multi-step reasoning |
| `mistral:latest` | 4.1 GB | ⭐ Fast, reliable, stays on task |
| `qwen2.5-coder` | 4.7 GB | ⭐ Coding and dev tasks |
| `deepseek-r1` | 4.7 GB | ⭐ Thorough reasoning |
| `gemma2:2b` | 1.6 GB | Lightweight, good for simple tasks |
| `phi3:mini` | 2.2 GB | Very fast, occasional JSON issues |
| Models under ~1B params | — | ⚠️ Too small, unreliable JSON output |

> **Tip:** `llama3.1` or `mistral` give the best balance of speed and reliability for agentic tasks.

---

## Custom Instructions

Open the menu and choose **option 6** to add persistent instructions that are injected into the agent's system prompt on every run. Examples:

```
prefer python3 over python
always use pip3
my projects folder is ~/Documents/projects
never use sudo without asking me first
```

Settings are saved to `~/.ollama_terminal_config.json`.

---

## How It Works

1. You describe a task in plain English
2. Your real username, home dir, OS, and shell are automatically injected so the agent always uses correct paths
3. The agent sends the task to your local Ollama model, requiring JSON-only replies
4. The model replies with `{"action": "run", "command": "...", "reason": "..."}`
5. The command runs and streams all output live
6. stdout + stderr + exit code are fed back to the model
7. The model decides: fix the error, run the next command, ask a question, or declare done
8. This loops until the model confirms the task is complete with `{"action": "done", ...}`

---

## Example Tasks

```
check for system updates
create a git repo in ~/projects/myapp and make an initial commit
find all .tmp files in /var and delete them
install the httpie cli tool and test it against httpbin.org
show disk usage sorted by size
back up my Documents folder to ~/backups with today's date
set up a python venv in the current folder and install flask
```

---

## Configuration

Constants at the top of `ollama_terminal.py`:

```python
OLLAMA_BASE      = "http://localhost:11434"  # Ollama server address
MAX_ITERATIONS   = 60    # Max steps before giving up
MAX_JSON_RETRIES = 5     # Retries if model outputs bad JSON
MAX_HISTORY_MSGS = 16    # Messages kept in context window
```

---

## Troubleshooting

**`Cannot connect to Ollama`**
Run `ollama serve` in a terminal, or use menu option 7.

**Model keeps producing bad JSON**
Try a larger model. Models under ~3B parameters often struggle with strict JSON formatting.

**Command times out**
Default timeout is 120 seconds per command. Increase it in `run_cmd()` for long-running installs.

**Task loops without finishing**
Try rephrasing the task more specifically, or add context via Custom Instructions (option 6).

---

## License

MIT
