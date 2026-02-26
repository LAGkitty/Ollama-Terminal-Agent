[<img src="https://ko-fi.com/img/githubbutton_sm.svg">](https://ko-fi.com/lagkitty)

# 🤖 Ollama Terminal

An autonomous terminal agent powered by a **locally running Ollama model**.

Describe a task, it plans the steps, runs real shell commands, reads the output, fixes errors, and continues until the task is fully complete.

✅ 100% local  
✅ No API keys  
✅ No cloud  
✅ No data leaves your machine  

<sub>If you don’t trust this `.py` file, you can upload it to any AI or review tool and verify that it’s safe.</sub>

---

## 🖥 Full Demo

```
╔══════════════════════════════════════════╗
║    🤖   O L L A M A   T E R M I N A L   ║
╚══════════════════════════════════════════╝

● Ollama: running   2 model(s)

Main Menu
──────────────────────────────────────────────────────────
1. ▶ Run Task              auto-select model
2. ⚙ Run Task              choose model manually
3. ⭐ Saved Tasks
4. ↓ Pull a Model
5. ✓ System Check
6. ✏ Custom Instructions
7. ⟳ Start Ollama
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

Step 1  explore home directory
┌─ $ ls /home/alex
│ Desktop  Documents  Downloads  Music  Pictures
└─ ✓

Step 2  create project folder
┌─ $ mkdir -p /home/alex/Documents/weather-cli
└─ ✓

Step 3  create virtual environment
┌─ $ python3 -m venv /home/alex/Documents/weather-cli/venv
└─ ✓

Step 4  install requests into venv
┌─ $ /home/alex/Documents/weather-cli/venv/bin/pip install requests
│ Successfully installed requests
└─ ✓

Step 5  write hello world script

❓ Agent asks: Should the script print to stdout or write to a log file?
   Your answer: stdout is fine

┌─ $ printf 'print("Hello from weather-cli!")\n' > /home/alex/Documents/weather-cli/main.py
└─ ✓

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
```

(Alex is just an example name.)

---

## 🚀 What It Can Do

- Create projects  
- Install packages  
- Manage files  
- Debug errors  
- Run system maintenance  
- Use web search when needed  
- Break large tasks into safe, small steps  

Everything runs in your real shell.

---

## ✨ Core Features

- Autonomous execution loop  
- Live streaming command output  
- Self-correcting error handling  
- Strict JSON action format  
- Automatically detects:
  - Username  
  - Home directory  
  - Operating system  
  - Shell  
  - Current working directory  
  - Available package managers  
- Saved tasks  
- Custom persistent instructions  
- Auto-starts Ollama if needed  
- Works with most Ollama models  

---

## 📦 Requirements

- Python 3.8+  
- Ollama installed  
- `requests` library  

Install dependency:

```bash
pip install requests
```

Pull at least one model:

```bash
ollama pull llama3
```

---

## ▶ Usage

Interactive menu:

```bash
python ollama_terminal.py
```

Run a task directly:

```bash
python ollama_terminal.py "find all .log files older than 7 days and delete them"
```

Choose a model manually:

```bash
python ollama_terminal.py -m mistral "check for flatpak updates"
```

System check:

```bash
python ollama_terminal.py --check
```

---

## ⚙ Configuration

Inside `ollama_terminal.py`:

```python
OLLAMA_BASE      = "http://localhost:11434"
MAX_ITERATIONS   = 60
MAX_JSON_RETRIES = 5
MAX_HISTORY_MSGS = 16
```

You can adjust these if needed.

---

## 🧠 How It Works (Simple)

1. You describe a task.  
2. The model replies in strict JSON:
   ```json
   {"action":"run","command":"...","reason":"..."}
   ```
3. The script runs the command.  
4. The output is sent back to the model.  
5. The loop continues until:
   ```json
   {"action":"done","summary":"..."}
   ```

The model must verify success before finishing.

---

## 🧩 Recommended Models

- `llama3` — reliable all-rounder  
- `llama3.1` — strong reasoning  
- `mistral` — fast and stable  
- `qwen2.5-coder` — coding tasks  
- `deepseek-r1` — thorough reasoning  

⚠ Very small models (<1B parameters) may struggle with strict JSON formatting.

---

## 🛡 Security Note

This tool executes **real shell commands**.

Be specific with tasks.  
Avoid vague destructive instructions such as:

```
clean my system
optimize everything
delete unused stuff
```

Always review what you are asking it to do.

---

## 📄 License

MIT
