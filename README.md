# 🤖 Ollama Terminal

An autonomous terminal agent powered by a **locally running Ollama model**.

Describe a goal in plain English — the agent plans the steps, executes real shell commands, reads the output, self-corrects on errors, and continues until the task is truly complete.

✅ 100% local  
✅ No API keys  
✅ No cloud  
✅ No data leaves your machine  

---

## 🚀 What It Does

`ollama_terminal.py` turns your local LLM into a self-correcting command-line agent that can:

- Create projects
- Install software
- Manage files
- Debug issues
- Run system maintenance
- Automate multi-step workflows

All directly inside your real shell environment.

---

## 🖥 Demo

```
╔══════════════════════════════════════════╗
║    🤖   O L L A M A   T E R M I N A L   ║
╚══════════════════════════════════════════╝

● Ollama: running   2 model(s)

Main Menu
──────────────────────────────────────────
1. ▶ Run Task              auto-select model
2. ⚙ Run Task              choose model manually
3. ⭐ Saved Tasks
4. ↓ Pull a Model
5. ✓ System Check
6. ✏ Custom Instructions
7. ⟳ Start Ollama
0. Exit
──────────────────────────────────────────
Choice: 1

Auto-selected: llama3:latest

What do you want me to do?
> set up a python project called weather-cli with a venv, install requests, and write a hello world script
```

The agent will:

- Explore directories
- Create folders
- Create virtual environments
- Install dependencies
- Write files
- Verify output
- Fix errors if needed
- Declare completion only when everything works

---

## ✨ Features

### 🧠 Autonomous Execution Loop
- Model replies in strict JSON
- Executes commands
- Streams live stdout/stderr
- Feeds results back to model
- Repeats until task is done

---

### 🔄 Self-Correcting
If a command fails:
- The error is sent back to the model
- The model adjusts strategy
- It never repeats the exact same failing command

---

### 📡 Live Streaming Output
Every command prints output line-by-line in real time.

---

### ⚙ Smart System Awareness
Automatically injects:
- Your username
- Home directory
- Operating system
- Default shell
- Current working directory
- Detected package managers

So paths are always correct.

---

### 🔍 Built-in Web Search (Optional)
- Uses DuckDuckGo via `ddgs`
- Auto-installs if missing
- Falls back gracefully if unavailable

---

### 🛠 Custom Instructions
Persistent rules stored in:

```
~/.ollama_terminal_config.json
```

Examples:

```
prefer python3 over python
always use pip3
never use sudo without asking me
my projects folder is ~/Documents/projects
```

---

### 💾 Saved Tasks
Save commonly used tasks and re-run instantly.

---

### 🤖 Auto Model Selection
- Picks the best installed model automatically
- Or manually choose one

---

### 🔄 JSON Recovery System
If malformed JSON is produced:
- Retries up to `MAX_JSON_RETRIES`
- Hard resets after limit

---

### 🧹 Context Trimming
Prevents context window overflow by limiting conversation history (`MAX_HISTORY_MSGS`).

---

## 📦 Requirements

- Python 3.8+
- Ollama installed
- `requests` Python library

Install dependency:

```bash
pip install requests
```

---

## 📥 Installation

```bash
git clone https://github.com/yourname/ollama-terminal.git
cd ollama-terminal

pip install requests

# Pull at least one model
ollama pull llama3

# Run
python ollama_terminal.py
```

---

## 🧑‍💻 Usage

### Interactive Mode (Recommended)

```bash
python ollama_terminal.py
```

---

### Direct Task Mode

```bash
python ollama_terminal.py "find all .log files older than 7 days and delete them"
```

Specify model manually:

```bash
python ollama_terminal.py -m mistral "check for flatpak updates"
```

---

### System Check

```bash
python ollama_terminal.py --check
```

---

## 🧠 How It Works Internally

1. You describe a task.
2. System context (user, OS, shell, home dir) is injected.
3. Model is forced to reply in strict JSON:
   ```json
   {
     "action": "run",
     "command": "...",
     "reason": "..."
   }
   ```
4. Command executes with live streaming.
5. Output + exit code sent back to model.
6. Model decides next action:
   - run another command
   - ask a question
   - fix an error
   - declare done
7. Loop continues until:
   ```json
   {
     "action": "done",
     "summary": "..."
   }
   ```

---

## 🧪 Example Tasks

```
check for system updates
create a git repo in ~/projects/myapp and make an initial commit
find all .tmp files in /var and delete them
install the httpie cli tool
show disk usage sorted by size
back up my Documents folder to ~/backups with today's date
set up a python venv in the current folder and install flask
```

---

## ⚙ Configuration (Inside `ollama_terminal.py`)

```python
OLLAMA_BASE      = "http://localhost:11434"
MAX_ITERATIONS   = 60
MAX_JSON_RETRIES = 5
MAX_HISTORY_MSGS = 16
```

Adjust these if needed.

---

## 🧩 Recommended Models

| Model | Best For |
|-------|----------|
| llama3:latest | Reliable all-rounder |
| llama3.1 | Strong multi-step reasoning |
| mistral | Fast and stable |
| qwen2.5-coder | Dev-heavy tasks |
| deepseek-r1 | Deep reasoning |
| gemma2:2b | Lightweight tasks |

⚠ Models under ~1B parameters often struggle with strict JSON formatting.

---

## 🛠 Troubleshooting

### Cannot connect to Ollama
Run:

```bash
ollama serve
```

Or use menu option 7.

---

### Model produces bad JSON
Use a larger model (≥ 3B parameters recommended).

---

### Command timeout
Default timeout is 120 seconds per command.
Modify inside `run_cmd()` if needed.

---

### Task loops forever
- Rephrase task more specifically.
- Add Custom Instructions.
- Increase `MAX_ITERATIONS`.

---

## 🔐 Security Note

This tool executes **real shell commands**.

Only run tasks you understand.

Avoid vague destructive instructions like:

```
clean my system
optimize everything
delete unused stuff
```

Be specific.

---

## 📄 License

MIT
