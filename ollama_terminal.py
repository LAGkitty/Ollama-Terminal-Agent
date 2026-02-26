#!/usr/bin/env python3
"""
Ollama Terminal — autonomous shell agent
"""

import subprocess, json, sys, os, time, argparse, re, shutil, threading
import urllib.request, urllib.parse, html

# ── Bootstrap: only stdlib needed to start. Everything else installed via check ──
def _ensure(pkg, import_as=None):
    """Silently try importing; return True if available."""
    try:
        __import__(import_as or pkg); return True
    except ImportError:
        return False

# Lazy-load optional deps — available after system_check installs them
requests          = None   # filled by _load_requests()
DDGS              = None   # filled by _load_ddgs()
WEB_AVAILABLE     = False

def _load_requests():
    global requests
    if requests is not None: return True
    try:
        import importlib, site
        importlib.invalidate_caches()
        # Ensure --user site-packages is on path
        try:
            for p in [site.getusersitepackages()] if isinstance(site.getusersitepackages(), str) else site.getusersitepackages():
                if p not in sys.path: sys.path.insert(0, p)
        except Exception: pass
        import requests as _r; requests = _r; return True
    except ImportError:
        return False

def _load_ddgs():
    global DDGS, WEB_AVAILABLE
    if WEB_AVAILABLE and DDGS is not None: return True
    try:
        import importlib, site
        importlib.invalidate_caches()
        # Ensure --user site-packages is on path (covers pyenv, venv, --user installs)
        try:
            usp = site.getusersitepackages()
            paths = [usp] if isinstance(usp, str) else usp
            for p in paths:
                if p and p not in sys.path: sys.path.insert(0, p)
        except Exception: pass
        # Remove stale cache entries if any (old and new names)
        for k in list(sys.modules.keys()):
            if "duckduckgo" in k.lower() or "ddgs" in k.lower():
                del sys.modules[k]
        from ddgs import DDGS as _D
        DDGS = _D; WEB_AVAILABLE = True; return True
    except ImportError:
        return False

# Try loading at startup — works fine if already installed
_load_requests()
_load_ddgs()

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
You are an autonomous shell agent on Linux. You have access to web search and shell commands.

REPLY FORMAT — always output exactly one JSON object, nothing else:
  Search web  : {"action": "search", "query": "...",   "reason": "..."}
  Fetch a URL : {"action": "fetch",  "url": "...",     "reason": "..."}
  Run command : {"action": "run",    "command": "...", "reason": "..."}
  Task done   : {"action": "done",   "summary": "..."}
  Ask user    : {"action": "ask",    "question": "..."}

══ COMMAND FIRST ══
Use your own knowledge of common packages and commands first. Try them directly.
Web search is OPTIONAL — only use it if you truly don't know the command or need verification.

══ DOWNLOAD RULES ══
- After curl/wget always run: ls -lh <filename>
- File under 1KB = download FAILED (got redirect/error page), not success
- If download looks wrong: search for the correct direct asset URL
- GitHub: look for the actual release asset URL, not the page URL
- Use curl -L (follow redirects) for GitHub and most downloads

══ COMMAND RULES ══
- Output ONLY the JSON object. No prose, no markdown, no backticks.
- One command per step. Keep it simple.
- Full absolute paths always.
- For file moves: for f in /path/*.ext; do mv "$f" /dest/; done
- If a package manager command fails (e.g., pamac not found), try alternatives: pacman, apt, dnf, or uninstall via direct paths.
- Always try at least 2 different approaches before searching.
- Use non-interactive flags to avoid prompts: pacman use --noconfirm, apt use -y, dnf use -y
- For pacman: "pacman -R <pkg>" → use "pacman -Rn --noconfirm <pkg>" instead (no interactive prompt)

══ ON FAILURE ══
- Never repeat the same failed command.
- Try a different approach or search if stuck.
- Break complex steps into smaller ones.

══ FINISHING ══
- Verify with ls -lh or which or cat before marking done.
- {"action":"done"} only when fully confirmed.\
"""

RETRY_PROMPT = ('BAD JSON. Reply with ONLY a raw JSON object. No text before or after. '
                'Example: {"action":"run","command":"ls /tmp","reason":"explore"}')

# ─────────────────────────────────────────────────────────────────────────────
# Web search + fetch (no API key — uses DuckDuckGo HTML scrape)
# ─────────────────────────────────────────────────────────────────────────────
def web_search(query, max_results=6):
    """Search DuckDuckGo with retry. Falls back to a note if unavailable."""
    import warnings
    _load_ddgs()
    if not WEB_AVAILABLE or DDGS is None:
        return None   # caller handles this

    last_err = ""
    for attempt in range(3):
        try:
            if attempt > 0:
                time.sleep(2)
            # Suppress deprecation warnings from ddgs package
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, max_results=max_results))
            if results:
                return [{"title": r.get("title",""), "url": r.get("href",""),
                         "snippet": r.get("body","")} for r in results]
        except Exception as e:
            last_err = str(e)

    return [{"title": f"Search failed after 3 attempts: {last_err}",
             "url": "", "snippet": "Try fetching the project homepage directly."}]

def web_fetch(url, max_chars=3000):
    """Fetch a URL and return cleaned plain text."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent":
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        # Strip tags
        text = re.sub(r'<script[^>]*>.*?</script>', '', raw, flags=re.DOTALL|re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>',  '', text, flags=re.DOTALL|re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html.unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars]
    except Exception as e:
        return f"Fetch error: {e}"

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
    if not _load_requests(): return False
    try: return requests.get(f"{OLLAMA_BASE}/api/tags",timeout=2).status_code==200
    except: return False

def _get_models():
    if not _load_requests(): return []
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
# System check — diagnoses AND auto-installs missing Python deps
# ─────────────────────────────────────────────────────────────────────────────
def _pip_install(pkg):
    """Install a pip package into user site. Returns True on success."""
    print(f"  {YL}  Installing {pkg}…{R}", flush=True)
    res = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--user", pkg],
        capture_output=True, text=True
    )
    if res.returncode == 0:
        print(f"  {GR}  ✓ {pkg} installed{R}")
        return True
    else:
        print(f"  {RD}  ✗ Failed: {res.stderr.strip()[-200:]}{R}")
        return False

def system_check(auto_install=True):
    banner()
    print(f"  {B}{WH}System Check{R}\n")
    issues = []
    installed_something = False

    def row(label, ok, ok_msg, fix_msg):
        sym = f"{GR}✓{R}" if ok else f"{RD}✗{R}"
        msg = f"{DIM}{ok_msg}{R}" if ok else f"{RD}{fix_msg}{R}"
        print(f"  {sym}  {B}{label:<26}{R} {msg}")
        if not ok: issues.append(label)

    # ── Python version ────────────────────────────────────────────────────────
    py_ok = sys.version_info >= (3, 8)
    row("Python 3.8+", py_ok, f"v{sys.version.split()[0]}", "Upgrade Python from python.org")

    # ── requests ─────────────────────────────────────────────────────────────
    req_ok = _ensure("requests")
    if not req_ok and auto_install:
        req_ok = _pip_install("requests")
        if req_ok: _load_requests(); installed_something = True
    row("requests", req_ok, "installed", "pip install requests")

    # ── ddgs (web search) ─────────────────────────────────────────────────────
    ddg_ok = _ensure("ddgs")
    if not ddg_ok and auto_install:
        print(f"\n  {YL}Web search not installed — installing now…{R}")
        ddg_ok = _pip_install("ddgs")
        if ddg_ok: _load_ddgs(); installed_something = True
    row("ddgs", ddg_ok,
        "installed — web search enabled",
        "will be auto-installed on next check")

    # ── ollama binary ─────────────────────────────────────────────────────────
    path = shutil.which("ollama") or ""
    row("ollama binary", bool(path), path, "Install: https://ollama.com/download")

    # ── ollama service ────────────────────────────────────────────────────────
    svc_ok = _ollama_running()
    if not svc_ok and shutil.which("ollama") and auto_install:
        print(f"\n  {YL}  Starting Ollama…{R}", end=" ", flush=True)
        subprocess.Popen(["ollama","serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(20):
            time.sleep(0.5)
            if _ollama_running(): svc_ok = True; break
        print(f"{GR}started{R}" if svc_ok else f"{RD}failed{R}")
    row("Ollama service", svc_ok, f"running at {OLLAMA_BASE}", "Run: ollama serve")

    # ── models ────────────────────────────────────────────────────────────────
    models = _get_models(); print()
    if models:
        print(f"  {GR}✓{R}  {B}Installed models{R}  {DIM}({len(models)}){R}")
        for m in models: print(f"       {DIM}• {m}{R}")
    else:
        print(f"  {YL}!{R}  {B}No models installed{R}")
        print(f"  {DIM}  Use menu option 4 to pull a model (e.g. llama3){R}")
        issues.append("models")

    # ── custom instructions status ────────────────────────────────────────────
    cfg = load_config(); ci = cfg.get("custom_instructions",""); print()
    if ci: print(f"  {GR}✓{R}  {B}Custom instructions{R}  {DIM}({len(ci)} chars){R}")
    else:  print(f"  {DIM}ℹ  No custom instructions set (option 6){R}")

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    if installed_something:
        print(f"  {GR}Installed missing packages — restart the script to activate them fully.{R}\n")
    if not issues:
        print(f"  {GR}{B}All checks passed ✓{R}\n")
    else:
        remaining = [i for i in issues if i not in ("duckduckgo-search","requests") or not installed_something]
        if remaining:
            print(f"  {YL}Issues remaining: {', '.join(remaining)}{R}\n")
        else:
            print(f"  {GR}All issues resolved ✓{R}\n")

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
            try:
                data = r.json()
                if not data or "message" not in data:
                    raise ValueError(f"Invalid response structure: {data}")
                return data["message"]["content"].strip()
            except (json.JSONDecodeError, ValueError) as je:
                raise RuntimeError(f"JSON parse error: {je} -- Response: {r.text[:200]}")
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
            try:
                data = r.json()
                if not data or "response" not in data:
                    raise ValueError(f"Invalid response structure: {data}")
                return data["response"].strip()
            except (json.JSONDecodeError, ValueError) as je:
                raise RuntimeError(f"JSON parse error: {je} -- Response: {r.text[:200]}")
    except requests.exceptions.HTTPError:
        # Raise instead of exiting so the caller can retry or handle it
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        # Raise generic runtime error for the caller to handle
        raise RuntimeError(f"API error: {e}")

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
    username = getpass.getuser()
    home     = os.path.expanduser("~")
    hostname = socket.gethostname()
    shell    = os.environ.get("SHELL", "/bin/bash")

    # ── Distro detection ──────────────────────────────────────────────────────
    distro = "unknown"
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    distro = line.split("=",1)[1].strip().strip('"')
                    break
    except Exception:
        distro = platform.platform()

    # ── Package manager detection ─────────────────────────────────────────────
    pkg_managers = []
    pm_hints = {}
    checks = [
        ("pacman",  "pacman",  "pacman -S <pkg>"),
        ("yay",     "yay",     "yay -S <pkg>"),
        ("paru",    "paru",    "paru -S <pkg>"),
        ("apt",     "apt",     "apt install <pkg>"),
        ("apt-get", "apt-get", "apt-get install <pkg>"),
        ("dnf",     "dnf",     "dnf install <pkg>"),
        ("zypper",  "zypper",  "zypper install <pkg>"),
        ("emerge",  "emerge",  "emerge <pkg>"),
        ("flatpak", "flatpak", "flatpak install flathub <pkg>"),
        ("snap",    "snap",    "snap install <pkg>"),
        ("brew",    "brew",    "brew install <pkg>"),
        ("pip3",    "pip3",    "pip3 install <pkg>"),
    ]
    for name, binary, cmd in checks:
        if shutil.which(binary):
            pkg_managers.append(name)
            pm_hints[name] = cmd

    pm_str = ", ".join(pkg_managers) if pkg_managers else "none detected"
    pm_detail = "\n".join(f"    {n}: {c}" for n,c in pm_hints.items())

    # ── Desktop environment ───────────────────────────────────────────────────
    desktop = os.environ.get("XDG_CURRENT_DESKTOP") or os.environ.get("DESKTOP_SESSION","unknown")

    # ── Architecture ─────────────────────────────────────────────────────────
    arch = platform.machine()

    web_note = "YES — web search active" if WEB_AVAILABLE else "NO — will auto-install on first search"

    env_block = (
        f"SYSTEM ENVIRONMENT — use these exact values, never guess:\n"
        f"  username    : {username}\n"
        f"  home dir    : {home}\n"
        f"  hostname    : {hostname}\n"
        f"  distro      : {distro}\n"
        f"  arch        : {arch}\n"
        f"  desktop     : {desktop}\n"
        f"  shell       : {shell}\n"
        f"  cwd         : {os.getcwd()}\n"
        f"  web search  : {web_note}\n"
        f"  pkg managers: {pm_str}\n"
        f"  install cmds:\n{pm_detail}"
    )

    cfg = load_config()
    ci  = cfg.get("custom_instructions","").strip()
    extras = f"\n\nCUSTOM INSTRUCTIONS:\n{ci}" if ci else ""
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

    # Detect if task likely needs a web search first
    search_kw = ["download","install","get","update","upgrade","find","latest",
                 "setup","build","compile","fetch","clone","pull","deploy","how"]
    likely_needs_search = any(w in task.lower() for w in search_kw)

    if likely_needs_search:
        first_msg = (
            f"Task: {task}\n\n"
            "If you know the command, run it directly. "
            "Use web search only if you're unsure about the package name or command. JSON only."
        )
    else:
        first_msg = (
            f"Task: {task}\n\n"
            "Proceed with the task using shell commands and your knowledge. JSON only."
        )

    messages=[
        {"role":"system","content":build_system_prompt()},
        {"role":"user","content":first_msg}
    ]

    step=0; consecutive_fails=0; spinner=None

    while step < MAX_ITERATIONS:
        step += 1

        # Start spinner ONLY when model is thinking, stop it before any output/input
        spinner = Spinner(f"Thinking  [step {step}]").start()
        try:
            raw = call_model(messages, model, url, mode)
        except Exception as e:
            # Ensure spinner is stopped before printing and retrying
            spinner.stop(); spinner = None
            print(f"  {RD}API call error: {e}{R}")
            consecutive_fails += 1
            if consecutive_fails >= 3:
                print(f"  {RD}Stopping after 3 consecutive API errors.{R}\n")
                return False
            # Give model a short hint and retry the loop
            messages += [{"role":"assistant","content":""},
                         {"role":"user","content":f"API error: {e}. Retry the last step. JSON only."}]
            time.sleep(2)
            continue
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
                "Try a different approach. Use your knowledge first, search only if needed. JSON only."}]
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
            
            # For package manager prompts, respond with 'yes' automatically and retry
            if any(kw in q.lower() for kw in ["remove", "delete", "want to"]):
                print(f"\n  {DIM}(Package manager confirmation detected — auto-responding 'yes'){R}")
                messages += [{"role":"assistant","content":raw},
                             {"role":"user","content":
                              "User confirmed 'yes'. Now retry the previous command with --noconfirm or -y flag to avoid interactive prompts. JSON only."}]
            else:
                # For other questions, ask the user
                print(f"\n  {YL}❓ Agent asks:{R} {q}")
                ans = input(f"  {YL}   Your answer:{R} ").strip()
                print()
                messages += [{"role":"assistant","content":raw},
                             {"role":"user","content":
                              f"{ans}\n\nContinue task now. Do NOT ask more questions. JSON only."}]

        # ── SEARCH ───────────────────────────────────────────────────────────
        elif action == "search":
            query  = parsed.get("query","").strip()
            reason = parsed.get("reason","")
            hr(w=62,ch="╌")
            print(f"  {MG}Step {step}{R}  {CY}🔍 Searching:{R} {DIM}{query}{R}")
            if not query:
                messages += [{"role":"assistant","content":raw},
                             {"role":"user","content":"Empty search query. Provide a search query."}]
                continue

            # Always attempt fresh load in case it was just pip-installed
            _load_ddgs()
            if not WEB_AVAILABLE:
                print(f"  {YL}│ ddgs not found — trying to install…{R}", flush=True)
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "--user", "ddgs"],
                    capture_output=True, text=True
                )
                if r.returncode == 0:
                    # After successful install, aggressively reload sys.path and module cache
                    import importlib, site
                    importlib.invalidate_caches()
                    # Clear all duckduckgo/ddgs modules from sys.modules
                    for k in list(sys.modules.keys()):
                        if 'duckduckgo' in k.lower() or 'ddgs' in k.lower():
                            del sys.modules[k]
                    # Ensure user site-packages is at front of sys.path
                    try:
                        usp = site.getusersitepackages()
                        paths = [usp] if isinstance(usp, str) else usp
                        for p in paths:
                            if p and p not in sys.path: sys.path.insert(0, p)
                    except Exception: pass
                    _load_ddgs()   # retry import after install with clean cache
                if not WEB_AVAILABLE:
                    print(f"  {RD}│ Could not load web search. Run system check (option 5).{R}")
                    print(f"  {YL}└─ skipped{R}\n")
                    feedback = (
                        "Web search is unavailable. Could not install ddgs automatically. "
                        "Ask the user to run system check from the menu. "
                        "Try to complete the task using your own knowledge. JSON only."
                    )
                    messages += [{"role":"assistant","content":raw},
                                 {"role":"user","content":feedback}]
                    continue
                else:
                    print(f"  {GR}│ Installed! Web search now active.{R}")

            spin = Spinner("Searching…").start()
            results = web_search(query)
            spin.stop()

            if results and results[0]["url"]:   # real results
                lines = []
                for i,r in enumerate(results,1):
                    if not r["url"]: continue
                    lines.append(f"[{i}] {r['title']}")
                    lines.append(f"    URL: {r['url']}")
                    if r["snippet"]: lines.append(f"    {r['snippet'][:300]}")
                    lines.append("")
                result_text = "\n".join(lines)
                print(f"  {GR}│{R} {GR}{len(results)} results{R}")
                print(f"  {GR}└─ ✓{R}\n")
                feedback = (
                    f"Search: {query}\n"
                    f"Results:\n{result_text}\n\n"
                    "Pick the most relevant result. Fetch its URL for more detail if needed, "
                    "then use the real URL/command from the page. JSON only."
                )
            else:
                err = results[0]["title"] if results else "No results"
                print(f"  {YL}│ {err}{R}")
                print(f"  {YL}└─ no results{R}\n")
                feedback = (
                    f"Search for \"{query}\" returned no useful results ({err}). "
                    "Try a different search query or fetch the project homepage directly. JSON only."
                )
            messages += [{"role":"assistant","content":raw},
                         {"role":"user","content":feedback}]

        # ── FETCH ─────────────────────────────────────────────────────────────
        elif action == "fetch":
            url    = parsed.get("url","").strip()
            reason = parsed.get("reason","")
            hr(w=62,ch="╌")
            print(f"  {MG}Step {step}{R}  {CY}🌐 Fetching:{R} {DIM}{url}{R}")
            if not url or not url.startswith("http"):
                print(f"  {RD}│ Invalid URL: {url!r}{R}\n")
                messages += [{"role":"assistant","content":raw},
                             {"role":"user","content":
                              f"Invalid URL {url!r}. Provide a real http/https URL to fetch. "
                              "If you don\'t have one, run a search first. JSON only."}]
                continue
            spin = Spinner("Fetching page…").start()
            page_text = web_fetch(url)
            spin.stop()
            print(f"  {GR}│{R} {len(page_text)} chars read")
            print(f"  {GR}└─ ✓{R}\n")
            feedback = (
                f"Fetched URL: {url}\n"
                f"Page content (truncated):\n{page_text}\n\n"
                "Use this information to proceed with the task. JSON only."
            )
            messages += [{"role":"assistant","content":raw},
                         {"role":"user","content":feedback}]

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
                # Detect interactive prompts in output (pacman, dpkg, etc.)
                interactive_markers = ["[Y/n]", "[y/N]", "Do you want to", "(y|n)", "[yes/no]"]
                has_interactive_prompt = any(marker in (stdout + stderr) for marker in interactive_markers)
                
                if has_interactive_prompt:
                    # Command succeeded but is waiting for user input
                    prompt_hint = ""
                    if "pacman" in cmd:
                        prompt_hint = "Retry with: pacman ... --noconfirm"
                    elif "apt" in cmd or "dpkg" in cmd:
                        prompt_hint = "Retry with: apt ... -y or DEBIAN_FRONTEND=noninteractive"
                    elif "dnf" in cmd or "yum" in cmd:
                        prompt_hint = "Retry with: dnf ... -y"
                    
                    feedback = (
                        f"RESULT: Waiting for user input\n"
                        f"Command: {cmd}\nstdout:\n{stdout}\nstderr:\n{stderr}\n\n"
                        f"The command is asking for confirmation. {prompt_hint}\n"
                        "Retry the command with non-interactive flags (--noconfirm, -y, etc) to avoid this.\n"
                        "Reply JSON only."
                    )
                else:
                    # Detect silent download failures (tiny file = error page, not real content)
                    silent_fail_hint = ""
                    if any(x in cmd for x in ["curl","wget"]) and "http" in cmd:
                        silent_fail_hint = (
                            "\nIMPORTANT: If this was a download, check the file size with ls -lh. "
                            "A file smaller than 1 KB means the download FAILED (got an error page). "
                            "If so, search the web for the correct direct download URL and retry."
                        )
                    feedback=(
                        f"RESULT: SUCCESS\nCommand: {cmd}\nstdout:\n{stdout}\nstderr:\n{stderr}\n\n"
                        + silent_fail_hint +
                        "\nIs the full task now complete?\n"
                        '- Yes: {"action":"done","summary":"..."}\n'
                        '- No:  next command as JSON. Do NOT ask questions.'
                    )
            else:
                feedback=(
                    f"RESULT: FAILED (exit {result['returncode']})\n"
                    f"Command: {cmd}\nstdout:\n{stdout}\nstderr:\n{stderr}\n\n"
                    "FAILED. Do NOT repeat this command.\n"
                    "Options:\n"
                    "1. Search the web for this error to find the correct approach.\n"
                    "2. Try a simpler alternative command.\n"
                    "3. If the URL/package was guessed, search for the real one.\n"
                    "Reply JSON only."
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
