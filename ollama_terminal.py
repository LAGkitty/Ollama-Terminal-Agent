#!/usr/bin/env python3
"""
Ollama Terminal — autonomous shell agent
"""

import subprocess, json, requests, sys, os, time, argparse, re, shutil, threading

# ── Colors ────────────────────────────────────────────────────────────────────
R="\033[0m"; B="\033[1m"; DIM="\033[2m"
CY="\033[96m"; GR="\033[92m"; YL="\033[93m"
RD="\033[91m"; BL="\033[94m"; WH="\033[97m"; MG="\033[95m"

# ── Config ────────────────────────────────────────────────────────────────────
OLLAMA_BASE      = "http://localhost:11434"
MAX_ITERATIONS   = 60
MAX_JSON_RETRIES = 5
MAX_HISTORY_MSGS = 16    # keep last N user/assistant pairs to avoid context overflow
CONFIG_FILE      = os.path.expanduser("~/.ollama_terminal_config.json")

# ── Load/save user config ─────────────────────────────────────────────────────
def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f: return json.load(f)
        except: pass
    return {"custom_instructions": "", "saved_tasks": []}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f: json.dump(cfg, f, indent=2)

# ── Prompts ───────────────────────────────────────────────────────────────────
BASE_SYSTEM_PROMPT = """\
You are an autonomous shell agent on Linux. Complete tasks by running shell commands.

REPLY FORMAT — always output exactly one JSON object, nothing else:
  Run a command : {"action": "run",  "command": "...", "reason": "..."}
  Task is done  : {"action": "done", "summary": "..."}
  Ask the user  : {"action": "ask",  "question": "..."}

RULES:
- Output ONLY the JSON object. Zero prose, zero markdown, zero backticks.
- One command per reply. Keep commands simple.
- Move files with bash for-loops, never xargs -I with -n:
    for f in /path/*.ext; do mv "$f" /dest/; done
- Write files with: printf 'text' > file.txt
- Use full absolute paths always.
- Before acting on a directory, run ls to see what's there.

ON FAILURE (exit code != 0):
- Never repeat the failed command.
- Try a simpler alternative. Break complex steps into smaller ones.

ASKING QUESTIONS:
- Only use {"action":"ask"} when you genuinely cannot proceed without more info.
- Do NOT ask for confirmation. Just do the task.
- Do NOT ask "do you want me to..." — assume yes and proceed.

FINISHING:
- Verify success before marking done (ls, cat, etc.).
- Use {"action":"done"} only when fully confirmed complete.\
"""

RETRY_PROMPT = ('BAD JSON. Reply with ONLY a raw JSON object. No text before or after. '
                'Example: {"action":"run","command":"ls /tmp","reason":"explore"}')

# ─────────────────────────────────────────────────────────────────────────────
# Spinner — stops cleanly before any input() call
# ─────────────────────────────────────────────────────────────────────────────
class Spinner:
    FRAMES = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    def __init__(self, msg="Thinking"):
        self.msg = msg
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._spin, daemon=True)
    def _spin(self):
        i = 0
        while not self._stop.is_set():
            f = self.FRAMES[i % len(self.FRAMES)]
            sys.stdout.write(f"\r  {CY}{f}{R} {DIM}{self.msg}…{R}   ")
            sys.stdout.flush()
            time.sleep(0.08); i += 1
    def start(self):
        self._stop.clear()
        self._t = threading.Thread(target=self._spin, daemon=True)
        self._t.start()
        return self
    def stop(self):
        self._stop.set()
        self._t.join()
        sys.stdout.write(f"\r{' '*60}\r")
        sys.stdout.flush()

# ─────────────────────────────────────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────────────────────────────────────
def clear(): os.system("clear")
def hr(w=62, ch="─"): print(DIM + ch*w + R)

def banner():
    clear(); print()
    print(f"{CY}{B}  ╔══════════════════════════════════════════╗{R}")
    print(f"{CY}{B}  ║    🤖   O L L A M A   T E R M I N A L   ║{R}")
    print(f"{CY}{B}  ╚══════════════════════════════════════════╝{R}")
    print()

def status_bar():
    running = _ollama_running(); models = _get_models()
    dot = f"{GR}●{R}" if running else f"{RD}●{R}"
    srv = f"{GR}running{R}" if running else f"{RD}stopped{R}"
    ml  = f"{GR}{len(models)} model(s){R}" if models else f"{YL}no models{R}"
    cfg = load_config()
    ci  = f"  {DIM}[custom instructions]{R}" if cfg.get("custom_instructions") else ""
    print(f"  {dot} Ollama: {srv}   {ml}{ci}\n")

def pick(title, options, allow_back=True):
    while True:
        print(f"  {B}{WH}{title}{R}"); hr()
        for i,(label,_) in enumerate(options,1):
            print(f"  {CY}{i}{R}. {label}")
        if allow_back: print(f"  {DIM}0. ← Back{R}")
        hr()
        raw = input(f"  {YL}Choice:{R} ").strip()
        if raw=="0" and allow_back: return None
        if raw.isdigit() and 1<=int(raw)<=len(options):
            return options[int(raw)-1][1]
        print(f"  {RD}Invalid.{R}\n")

# ─────────────────────────────────────────────────────────────────────────────
# Ollama service
# ─────────────────────────────────────────────────────────────────────────────
def _ollama_running():
    try: return requests.get(f"{OLLAMA_BASE}/api/tags",timeout=2).status_code==200
    except: return False

def _get_models():
    try:
        r=requests.get(f"{OLLAMA_BASE}/api/tags",timeout=2)
        if r.status_code==200: return [m["name"] for m in r.json().get("models",[])]
    except: pass
    return []

def ensure_running():
    if _ollama_running(): return True
    if not shutil.which("ollama"):
        print(f"\n  {RD}ollama not found. Install: https://ollama.com/download{R}\n")
        return False
    print(f"  {YL}Starting Ollama…{R}", end=" ", flush=True)
    subprocess.Popen(["ollama","serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(24):
        time.sleep(0.5)
        if _ollama_running(): print(f"{GR}started!{R}"); return True
    print(f"{RD}failed.{R}\n  Run:  {CY}ollama serve{R}\n"); return False

def auto_model():
    models=_get_models()
    if not models: return None
    for pref in ["llama3","mistral","gemma","phi","qwen"]:
        for m in models:
            if pref in m.lower(): return m
    return models[0]

# ─────────────────────────────────────────────────────────────────────────────
# Custom instructions
# ─────────────────────────────────────────────────────────────────────────────
def edit_instructions():
    banner()
    cfg = load_config(); current = cfg.get("custom_instructions","")
    print(f"  {B}{WH}Custom Instructions{R}\n")
    print(f"  Added to the agent's system prompt on every run.")
    print(f"  Examples: your preferred tools, coding style, OS details.\n")
    if current:
        print(f"  {B}Current:{R}"); hr(w=50,ch="╌")
        for line in current.split("\n"): print(f"  {DIM}{line}{R}")
        hr(w=50,ch="╌"); print()
    print(f"  {CY}1{R}. Edit / replace")
    print(f"  {CY}2{R}. Clear")
    print(f"  {CY}0{R}. {DIM}Back{R}\n")
    c = input(f"  {YL}Choice:{R} ").strip()
    if c=="1":
        print(f"\n  {DIM}Type instructions. Blank line twice to finish.{R}\n")
        lines=[]
        try:
            while True:
                line=input("  ")
                if line=="" and lines and lines[-1]=="": break
                lines.append(line)
        except EOFError: pass
        cfg["custom_instructions"]="\n".join(lines).strip()
        save_config(cfg); print(f"\n  {GR}✓ Saved.{R}\n")
    elif c=="2":
        cfg["custom_instructions"]=""; save_config(cfg)
        print(f"\n  {YL}Cleared.{R}\n")
    input(f"  {DIM}Press Enter…{R}")

# ─────────────────────────────────────────────────────────────────────────────
# Saved tasks
# ─────────────────────────────────────────────────────────────────────────────
def saved_tasks_menu():
    banner(); cfg=load_config(); tasks=cfg.get("saved_tasks",[])
    print(f"  {B}{WH}Saved Tasks{R}\n")
    if not tasks:
        print(f"  {DIM}No saved tasks yet. Tasks can be saved after completion.{R}\n")
    else:
        for i,t in enumerate(tasks,1): print(f"  {CY}{i}{R}. {t}")
        print()
    print(f"  {CY}a{R}. Add task")
    if tasks: print(f"  {CY}d{R}. Delete task")
    print(f"  {CY}0{R}. {DIM}Back{R}\n")
    c=input(f"  {YL}Choice:{R} ").strip().lower()
    if c=="a":
        t=input(f"\n  {YL}Task text:{R} ").strip()
        if t: tasks.append(t); cfg["saved_tasks"]=tasks; save_config(cfg)
        print(f"  {GR}✓ Saved.{R}\n")
    elif c=="d" and tasks:
        n=input(f"\n  {YL}Delete number:{R} ").strip()
        if n.isdigit() and 1<=int(n)<=len(tasks):
            removed=tasks.pop(int(n)-1); cfg["saved_tasks"]=tasks; save_config(cfg)
            print(f"  {GR}✓ Removed: {removed}{R}\n")
    input(f"  {DIM}Press Enter…{R}")

# ─────────────────────────────────────────────────────────────────────────────
# System check
# ─────────────────────────────────────────────────────────────────────────────
def system_check():
    banner(); print(f"  {B}{WH}System Check{R}\n"); ok_all=True
    def row(label,ok,ok_msg,fix_msg):
        nonlocal ok_all
        sym=f"{GR}✓{R}" if ok else f"{RD}✗{R}"
        msg=f"{DIM}{ok_msg}{R}" if ok else f"{RD}{fix_msg}{R}"
        print(f"  {sym}  {B}{label:<22}{R} {msg}")
        if not ok: ok_all=False
    row("Python 3.8+",sys.version_info>=(3,8),f"v{sys.version.split()[0]}","Upgrade Python")
    try: import requests as _r; row("requests lib",True,"installed","")
    except ImportError: row("requests lib",False,"","pip install requests")
    path=shutil.which("ollama") or ""
    row("ollama binary",bool(path),path or "not found","Install: https://ollama.com/download")
    row("Ollama service",_ollama_running(),f"OK at {OLLAMA_BASE}","Run: ollama serve")
    models=_get_models(); print()
    if models:
        print(f"  {GR}✓{R}  {B}Installed models{R}  {DIM}({len(models)}){R}")
        for m in models: print(f"       {DIM}• {m}{R}")
    else:
        print(f"  {YL}!{R}  {B}No models{R}  {DIM}Run: ollama pull llama3{R}"); ok_all=False
    cfg=load_config(); ci=cfg.get("custom_instructions",""); print()
    if ci: print(f"  {GR}✓{R}  {B}Custom instructions{R}  {DIM}set ({len(ci)} chars){R}")
    else:  print(f"  {DIM}ℹ  No custom instructions (menu option 6){R}")
    print()
    print(f"  {GR}{B}All checks passed ✓{R}\n" if ok_all else f"  {YL}Some issues — see above.{R}\n")
    input(f"  {DIM}Press Enter…{R}")

# ─────────────────────────────────────────────────────────────────────────────
# Pull menu
# ─────────────────────────────────────────────────────────────────────────────
def pull_menu():
    banner()
    popular=[
        ("llama3:latest      4.7 GB  ★ great all-rounder",       "llama3"),
        ("llama3.1:latest    4.9 GB  ★ better reasoning",         "llama3.1"),
        ("mistral:latest     4.1 GB  ★ fast, stays on task",      "mistral"),
        ("qwen2.5-coder      4.7 GB  ★ best for code/dev tasks",  "qwen2.5-coder"),
        ("deepseek-r1        4.7 GB  ★ thorough reasoning",       "deepseek-r1"),
        ("gemma2:2b          1.6 GB    lightweight",              "gemma2:2b"),
        ("phi3:mini          2.2 GB    fast, occasional JSON issues","phi3:mini"),
        ("Custom name…",                                          "__custom__"),
    ]
    choice=pick("Pull a Model  (★ = recommended for agent tasks)",popular)
    if choice is None: return
    if choice=="__custom__": choice=input(f"\n  {YL}Model name:{R} ").strip()
    if choice:
        print(f"\n  {CY}Pulling {choice}…{R}\n")
        subprocess.run(["ollama","pull",choice]); print()
    input(f"  {DIM}Press Enter…{R}")

# ─────────────────────────────────────────────────────────────────────────────
# Ollama API
# ─────────────────────────────────────────────────────────────────────────────
_ep_cache={}

def detect_endpoint(model):
    if model in _ep_cache: return _ep_cache[model]
    try:
        r=requests.post(f"{OLLAMA_BASE}/api/chat",
            json={"model":model,"messages":[{"role":"user","content":"hi"}],
                  "stream":False,"options":{"num_predict":1}},timeout=20)
        if r.status_code==200:
            _ep_cache[model]=(f"{OLLAMA_BASE}/api/chat","chat"); return _ep_cache[model]
    except: pass
    _ep_cache[model]=(f"{OLLAMA_BASE}/api/generate","generate"); return _ep_cache[model]

def trim_messages(messages):
    """Keep system prompt + last MAX_HISTORY_MSGS messages."""
    if len(messages) <= MAX_HISTORY_MSGS + 1: return messages
    return [messages[0]] + messages[-MAX_HISTORY_MSGS:]

def call_model(messages, model, url, mode):
    msgs = trim_messages(messages)
    try:
        if mode=="chat":
            r=requests.post(url,
                json={"model":model,"messages":msgs,"stream":False,
                      "options":{"temperature":0.05,"num_predict":400}},
                timeout=180)
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        else:
            parts=[]
            for m in msgs:
                tag="SYSTEM" if m["role"]=="system" else m["role"].upper()
                parts.append(f"{tag}:\n{m['content']}")
            parts.append("ASSISTANT:")
            r=requests.post(url,
                json={"model":model,"prompt":"\n\n".join(parts),"stream":False,
                      "options":{"temperature":0.05,"num_predict":400}},
                timeout=180)
            r.raise_for_status()
            return r.json()["response"].strip()
    except requests.exceptions.HTTPError:
        print(f"\n{RD}HTTP {r.status_code}: {r.text[:200]}{R}"); sys.exit(1)
    except Exception as e:
        print(f"\n{RD}API error: {e}{R}"); sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# JSON parser
# ─────────────────────────────────────────────────────────────────────────────
def parse_json(text):
    t = re.sub(r'^```(?:json)?\s*','',text.strip(),flags=re.IGNORECASE)
    t = re.sub(r'\s*```$','',t).strip()
    try: return json.loads(t)
    except: pass
    best=None
    for s in range(len(t)):
        if t[s]!='{': continue
        depth=0
        for e in range(s,len(t)):
            if t[e]=='{': depth+=1
            elif t[e]=='}':
                depth-=1
                if depth==0:
                    try:
                        obj=json.loads(t[s:e+1])
                        if "action" in obj: best=obj
                    except: pass
                    break
    return best

# ─────────────────────────────────────────────────────────────────────────────
# Shell runner — live streaming output
# ─────────────────────────────────────────────────────────────────────────────
def run_cmd(cmd, timeout=120):
    print(f"\n  {BL}┌─ $ {cmd}{R}")
    out_lines=[]; err_lines=[]
    try:
        proc=subprocess.Popen(cmd,shell=True,stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,text=True,cwd=os.getcwd())
        def reader(stream, lines, col):
            for raw in stream:
                line=raw.rstrip('\n'); lines.append(line)
                print(f"  {col}│{R} {line}", flush=True)
            stream.close()
        to=threading.Thread(target=reader,args=(proc.stdout,out_lines,GR),daemon=True)
        te=threading.Thread(target=reader,args=(proc.stderr,err_lines,RD),daemon=True)
        to.start(); te.start()
        try: proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill(); err_lines.append("Timed out.")
            print(f"  {RD}│ [timed out]{R}")
        to.join(); te.join()
        code=proc.returncode
    except Exception as e:
        code=-1; err_lines.append(str(e))
        print(f"  {RD}│ Error: {e}{R}")
    col=GR if code==0 else RD
    print(f"  {col}└─ {'✓' if code==0 else f'✗ exit {code}'}{R}\n")
    return {"stdout":"\n".join(out_lines),"stderr":"\n".join(err_lines),"returncode":code}

# ─────────────────────────────────────────────────────────────────────────────
# Agent loop
# ─────────────────────────────────────────────────────────────────────────────
def build_system_prompt():
    import getpass, platform, socket
    username  = getpass.getuser()
    home      = os.path.expanduser("~")
    hostname  = socket.gethostname()
    os_info   = platform.platform()
    shell     = os.environ.get("SHELL", "/bin/bash")

    env_block = (
        f"SYSTEM ENVIRONMENT (use these exact paths — never guess):\n"
        f"  username : {username}\n"
        f"  home dir : {home}\n"
        f"  hostname : {hostname}\n"
        f"  OS       : {os_info}\n"
        f"  shell    : {shell}\n"
        f"  cwd      : {os.getcwd()}"
    )

    cfg = load_config()
    ci  = cfg.get("custom_instructions","").strip()
    extras = ""
    if ci:
        extras += f"\n\nCUSTOM INSTRUCTIONS:\n{ci}"

    return BASE_SYSTEM_PROMPT + f"\n\n{env_block}" + extras

def run_agent(task, model):
    spin=Spinner("Connecting").start()
    url,mode=detect_endpoint(model)
    spin.stop()
    print(f"  {GR}Connected{R} {DIM}({mode}){R}\n")
    hr()
    print(f"  {B}Model:{R} {CY}{model}{R}")
    print(f"  {B}Task: {R} {WH}{task}{R}")
    hr(); print()

    messages=[
        {"role":"system","content":build_system_prompt()},
        {"role":"user","content":(
            f"Task: {task}\n\n"
            "First run ls on any target directory to see what's there. "
            "Do NOT ask for confirmation — just do the task. JSON only."
        )}
    ]

    step=0; consecutive_fails=0; spinner=None

    while step < MAX_ITERATIONS:
        step += 1

        # Start spinner ONLY when model is thinking, stop it before any output/input
        spinner = Spinner(f"Thinking  [step {step}]").start()
        raw = call_model(messages, model, url, mode)
        spinner.stop(); spinner = None   # ← stopped before we do anything else

        parsed = parse_json(raw)

        # ── JSON retry loop ───────────────────────────────────────────────────
        if parsed is None:
            for attempt in range(MAX_JSON_RETRIES):
                print(f"  {YL}⚠ Bad JSON (attempt {attempt+1}/{MAX_JSON_RETRIES})…{R}")
                messages += [{"role":"assistant","content":raw},
                             {"role":"user","content":RETRY_PROMPT}]
                spinner = Spinner("Retrying").start()
                raw = call_model(messages, model, url, mode)
                spinner.stop(); spinner = None
                parsed = parse_json(raw)
                if parsed: break

        if parsed is None:
            print(f"  {RD}Could not get valid JSON after {MAX_JSON_RETRIES} retries.{R}")
            consecutive_fails += 1
            if consecutive_fails >= 3:
                print(f"  {RD}Stopping after 3 consecutive failures.{R}\n"); break
            # Hard reset — wipe history, re-anchor
            messages = [messages[0], {"role":"user","content":
                f"Task (resume): {task}\n"
                "Run ls on the target path first. JSON only."}]
            continue

        consecutive_fails = 0
        action = parsed.get("action","run")

        # ── DONE ─────────────────────────────────────────────────────────────
        if action == "done":
            hr(ch="═")
            print(f"  {GR}{B}✓  Task complete!{R}")
            summary = parsed.get("summary","")
            if summary: print(f"\n  {WH}{summary}{R}")
            hr(ch="═"); print()
            ans = input(f"  {DIM}Save as a saved task? [y/N]:{R} ").strip().lower()
            if ans == "y":
                cfg = load_config()
                saved = cfg.setdefault("saved_tasks",[])
                if task not in saved: saved.append(task); save_config(cfg)
                print(f"  {GR}✓ Saved!{R}")
            print()
            return True

        # ── ASK ──────────────────────────────────────────────────────────────
        elif action == "ask":
            # Spinner is already stopped — safe to call input()
            q = parsed.get("question","?")
            print(f"\n  {YL}❓ Agent asks:{R} {q}")
            ans = input(f"  {YL}   Your answer:{R} ").strip()
            print()
            messages += [{"role":"assistant","content":raw},
                         {"role":"user","content":
                          f"{ans}\n\nContinue task now. Do NOT ask more questions. JSON only."}]

        # ── RUN ──────────────────────────────────────────────────────────────
        else:
            cmd    = parsed.get("command","").strip()
            reason = parsed.get("reason","")
            hr(w=62,ch="╌")
            print(f"  {MG}Step {step}{R}  {DIM}{reason}{R}")

            if not cmd:
                messages += [{"role":"assistant","content":raw},
                             {"role":"user","content":
                              'Empty command. Give {"action":"run","command":"...","reason":"..."}.'}]
                continue

            result = run_cmd(cmd)
            ok = result["returncode"] == 0

            # Trim output so it doesn't flood context
            stdout = result["stdout"][-2000:] if len(result["stdout"])>2000 else result["stdout"]
            stderr = result["stderr"][-800:]  if len(result["stderr"])>800  else result["stderr"]

            if ok:
                feedback=(
                    f"RESULT: SUCCESS\nCommand: {cmd}\nstdout:\n{stdout}\nstderr:\n{stderr}\n\n"
                    "Is the full task now complete?\n"
                    '- Yes: {"action":"done","summary":"..."}\n'
                    '- No:  next command as JSON. Do NOT ask questions.'
                )
            else:
                feedback=(
                    f"RESULT: FAILED (exit {result['returncode']})\n"
                    f"Command: {cmd}\nstdout:\n{stdout}\nstderr:\n{stderr}\n\n"
                    "Do NOT repeat this command.\n"
                    "Try something simpler. For file moves use:\n"
                    '{"action":"run","command":"for f in /path/*.ext; do mv \\"$f\\" /dest/; done","reason":"..."}\n'
                    "JSON only."
                )
            messages += [{"role":"assistant","content":raw},
                         {"role":"user","content":feedback}]

    print(f"\n  {YL}Reached step limit ({MAX_ITERATIONS}).{R}\n")
    return False

# ─────────────────────────────────────────────────────────────────────────────
# Main menu
# ─────────────────────────────────────────────────────────────────────────────
def main_menu():
    while True:
        banner(); status_bar()
        cfg=load_config(); saved=cfg.get("saved_tasks",[])
        print(f"  {B}{WH}Main Menu{R}"); hr()
        print(f"  {CY}1{R}. {B}▶  Run Task{R}              {DIM}auto-select model{R}")
        print(f"  {CY}2{R}. {B}⚙  Run Task{R}              {DIM}choose model manually{R}")
        stag = f"{DIM}({len(saved)} saved){R}" if saved else f"{DIM}(none yet){R}"
        print(f"  {CY}3{R}. {B}⭐  Saved Tasks{R}           {stag}")
        print(f"  {CY}4{R}. {B}↓  Pull a Model{R}")
        print(f"  {CY}5{R}. {B}✓  System Check{R}")
        print(f"  {CY}6{R}. {B}✏  Custom Instructions{R}   {DIM}add rules / context{R}")
        print(f"  {CY}7{R}. {B}⟳  Start Ollama{R}          {DIM}if stopped{R}")
        print(f"  {CY}0{R}. {DIM}Exit{R}")
        hr()
        c=input(f"  {YL}Choice:{R} ").strip(); print()

        if c in ("1","2"):
            if not ensure_running(): input(f"  {DIM}Press Enter…{R}"); continue
            if c=="1":
                model=auto_model()
                if not model:
                    print(f"  {RD}No models. Use option 4 first.{R}\n")
                    input(f"  {DIM}Press Enter…{R}"); continue
                print(f"  {DIM}Auto-selected:{R} {CY}{model}{R}\n")
            else:
                banner(); models=_get_models()
                if not models:
                    print(f"  {RD}No models. Use option 4 first.{R}\n")
                    input(f"  {DIM}Press Enter…{R}"); continue
                model=pick("Select Model",[(m,m) for m in models])
                if not model: continue
                print()
            task=input(f"  {B}What do you want me to do?{R}\n  > ").strip()
            if not task: continue
            print(); run_agent(task,model)
            input(f"  {DIM}Press Enter to return to menu…{R}")

        elif c=="3":
            if not saved: saved_tasks_menu(); continue
            if not ensure_running(): input(f"  {DIM}Press Enter…{R}"); continue
            banner()
            task=pick("Run Saved Task",[(t,t) for t in saved])
            if not task: continue
            model=auto_model()
            if not model:
                print(f"  {RD}No models. Use option 4 first.{R}\n")
                input(f"  {DIM}Press Enter…{R}"); continue
            print(f"  {DIM}Model:{R} {CY}{model}{R}\n")
            print(); run_agent(task,model)
            input(f"  {DIM}Press Enter to return to menu…{R}")

        elif c=="4":
            if not shutil.which("ollama"):
                print(f"  {RD}ollama not installed.{R}\n")
                input(f"  {DIM}Press Enter…{R}"); continue
            pull_menu()
        elif c=="5": system_check()
        elif c=="6": edit_instructions()
        elif c=="7": ensure_running(); input(f"\n  {DIM}Press Enter…{R}")
        elif c=="0": print(f"  {DIM}Bye!{R}\n"); sys.exit(0)

# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def main():
    p=argparse.ArgumentParser(description="Ollama Terminal Agent")
    p.add_argument("task",nargs="?"); p.add_argument("-m","--model",default=None)
    p.add_argument("--check",action="store_true"); args=p.parse_args()
    if args.check: system_check(); return
    if args.task:
        if not ensure_running(): sys.exit(1)
        model=args.model or auto_model()
        if not model: print(f"{RD}No models. Run: ollama pull llama3{R}"); sys.exit(1)
        run_agent(args.task,model); return
    try: main_menu()
    except KeyboardInterrupt: print(f"\n\n  {DIM}Bye!{R}\n")

if __name__=="__main__":
    main()
