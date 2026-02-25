#!/usr/bin/env python3
"""
Ollama Terminal — autonomous shell agent + autonomous task runner
"""

import subprocess, json, requests, sys, os, time, argparse, re, shutil, threading

# ── ANSI colors ───────────────────────────────────────────────────────────────
R  = "\033[0m";  B  = "\033[1m";  DIM= "\033[2m"
CY = "\033[96m"; GR = "\033[92m"; YL = "\033[93m"
RD = "\033[91m"; BL = "\033[94m"; WH = "\033[97m"; MG = "\033[95m"

OLLAMA_BASE      = "http://localhost:11434"
MAX_ITERATIONS   = 60
MAX_JSON_RETRIES = 5

SYSTEM_PROMPT = """You are an autonomous shell agent running on Linux/macOS.
Your ONLY job is to complete the user's task by running shell commands.

STRICT OUTPUT FORMAT — reply with ONLY a single JSON object, nothing else:
  To run a command:  {"action": "run",  "command": "...", "reason": "..."}
  When fully done:   {"action": "done", "summary": "..."}
  To ask the user:   {"action": "ask",  "question": "..."}

CRITICAL RULES:
- Output NOTHING except the JSON object. No prose, no markdown, no backticks.
- Run ONE command at a time. Do not chain with && unless very simple.
- For writing multi-line text to files, use printf or tee with a heredoc.
- Read EVERY command output carefully. If exit code != 0, fix the error.
- Verify success by checking file existence, content, etc. before marking done.
- Only use {"action":"done"} when you have CONFIRMED the task is complete.
- NEVER give up. Try alternative approaches if something fails.
"""

RETRY_PROMPT = ('Your last reply was not valid JSON. Reply with ONLY a raw JSON object. '
                'No explanation, no markdown fences, no extra text. Example: '
                '{"action":"run","command":"ls ~","reason":"list home"}')

# ─────────────────────────────────────────────────────────────────────────────
# Spinner
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
            print(f"\r  {CY}{f}{R} {DIM}{self.msg}…{R}   ", end="", flush=True)
            time.sleep(0.08); i += 1
    def start(self): self._t.start(); return self
    def stop(self):
        self._stop.set(); self._t.join()
        print(f"\r{' '*60}\r", end="", flush=True)

# ─────────────────────────────────────────────────────────────────────────────
# UI helpers
# ─────────────────────────────────────────────────────────────────────────────

def clear(): os.system("clear")
def hr(w=62, ch="─"): print(DIM + ch*w + R)

def banner():
    clear()
    print()
    print(f"{CY}{B}  ╔══════════════════════════════════════════╗{R}")
    print(f"{CY}{B}  ║    🤖   O L L A M A   A G E N T         ║{R}")
    print(f"{CY}{B}  ╚══════════════════════════════════════════╝{R}")
    print()

def status_bar():
    running = _ollama_running()
    models  = _get_models()
    dot = f"{GR}●{R}" if running else f"{RD}●{R}"
    srv = f"{GR}running{R}" if running else f"{RD}stopped{R}"
    ml  = f"{GR}{len(models)} model(s){R}" if models else f"{YL}no models{R}"
    print(f"  {dot} Ollama: {srv}   {ml}\n")

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
# Ollama service helpers
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
    print(f"  {YL}Starting Ollama…{R}",end=" ",flush=True)
    subprocess.Popen(["ollama","serve"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
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
    ver=sys.version.split()[0]
    row("Python 3.8+",sys.version_info>=(3,8),f"v{ver}","Upgrade Python")
    try: import requests as _; row("requests lib",True,"installed","")
    except ImportError: row("requests lib",False,"","pip install requests")
    path=shutil.which("ollama") or ""
    row("ollama binary",bool(path),path,"Install: https://ollama.com/download")
    row("Ollama service",_ollama_running(),f"OK at {OLLAMA_BASE}","Run: ollama serve")
    models=_get_models(); print()
    if models:
        print(f"  {GR}✓{R}  {B}Installed models{R}  {DIM}({len(models)}){R}")
        for m in models: print(f"       {DIM}• {m}{R}")
    else:
        print(f"  {YL}!{R}  {B}No models{R}  {DIM}Run: ollama pull llama3{R}"); ok_all=False
    print()
    msg=f"{GR}{B}All checks passed ✓{R}" if ok_all else f"{YL}Some issues — see fixes above.{R}"
    print(f"  {msg}\n"); input(f"  {DIM}Press Enter…{R}")

# ─────────────────────────────────────────────────────────────────────────────
# Pull menu
# ─────────────────────────────────────────────────────────────────────────────

def pull_menu():
    banner()
    popular=[
        ("llama3:latest      4.7 GB — best all-rounder","llama3"),
        ("llama3.1:latest    4.9 GB — better reasoning","llama3.1"),
        ("mistral:latest     4.1 GB — fast & smart","mistral"),
        ("gemma2:2b          1.6 GB — lightweight","gemma2:2b"),
        ("phi3:mini          2.2 GB — very fast","phi3:mini"),
        ("Custom name…","__custom__"),
    ]
    choice=pick("Pull a Model",popular)
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

def call_model(messages,model,url,mode):
    try:
        if mode=="chat":
            r=requests.post(url,
                json={"model":model,"messages":messages,"stream":False,
                      "options":{"temperature":0.05}},timeout=180)
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
        else:
            parts=[]
            for m in messages:
                tag="SYSTEM" if m["role"]=="system" else m["role"].upper()
                parts.append(f"{tag}:\n{m['content']}")
            parts.append("ASSISTANT:")
            r=requests.post(url,
                json={"model":model,"prompt":"\n\n".join(parts),"stream":False,
                      "options":{"temperature":0.05}},timeout=180)
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
    t=text.strip()
    # strip markdown fences
    t=re.sub(r'^```(?:json)?\s*','',t,flags=re.IGNORECASE)
    t=re.sub(r'\s*```$','',t).strip()
    try: return json.loads(t)
    except: pass
    # bracket scan — find last valid {"action":...} block
    best=None
    for start in range(len(t)):
        if t[start]!='{': continue
        depth=0
        for end in range(start,len(t)):
            if t[end]=='{': depth+=1
            elif t[end]=='}':
                depth-=1
                if depth==0:
                    try:
                        obj=json.loads(t[start:end+1])
                        if "action" in obj: best=obj
                    except: pass
                    break
    return best

# ─────────────────────────────────────────────────────────────────────────────
# Shell runner — streams output live
# ─────────────────────────────────────────────────────────────────────────────

def run_cmd(cmd, timeout=120):
    """Run command and stream every line of output in real time."""
    print(f"\n  {BL}┌─ $ {cmd}{R}")
    stdout_lines = []
    stderr_lines = []
    try:
        proc = subprocess.Popen(
            cmd, shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=os.getcwd()
        )

        # Use threads to read stdout and stderr simultaneously
        def read_stream(stream, lines, color):
            for raw_line in stream:
                line = raw_line.rstrip('\n')
                lines.append(line)
                print(f"  {color}│{R} {line}")
            stream.close()

        t_out = threading.Thread(target=read_stream,
                                 args=(proc.stdout, stdout_lines, GR))
        t_err = threading.Thread(target=read_stream,
                                 args=(proc.stderr, stderr_lines, RD))
        t_out.start(); t_err.start()

        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stderr_lines.append("Command timed out.")
            print(f"  {RD}│ [timed out]{R}")

        t_out.join(); t_err.join()
        code = proc.returncode

    except Exception as e:
        code = -1
        stderr_lines.append(str(e))
        print(f"  {RD}│ Error: {e}{R}")

    # status footer
    status_color = GR if code == 0 else RD
    status_sym   = "✓" if code == 0 else f"✗ exit {code}"
    print(f"  {status_color}└─ {status_sym}{R}\n")

    return {
        "stdout": "\n".join(stdout_lines),
        "stderr": "\n".join(stderr_lines),
        "returncode": code
    }

# ─────────────────────────────────────────────────────────────────────────────
# Agent loop
# ─────────────────────────────────────────────────────────────────────────────

def run_agent(task, model):
    spin=Spinner("Connecting").start()
    url,mode=detect_endpoint(model)
    spin.stop()
    print(f"  {GR}Connected{R} {DIM}({mode} mode){R}\n")
    hr()
    print(f"  {B}Model:{R} {CY}{model}{R}")
    print(f"  {B}Task: {R} {WH}{task}{R}")
    hr(); print()

    messages=[
        {"role":"system","content":SYSTEM_PROMPT},
        {"role":"user","content":f"Task: {task}\n\nBegin now. Reply with JSON only."}
    ]

    step=0
    consecutive_fails=0

    while step<MAX_ITERATIONS:
        step+=1

        # ── model call ───────────────────────────────────────────────────────
        spin=Spinner(f"Thinking  [step {step}]").start()
        raw=call_model(messages,model,url,mode)
        spin.stop()

        # ── parse with retries ───────────────────────────────────────────────
        parsed=parse_json(raw)
        for attempt in range(MAX_JSON_RETRIES):
            if parsed is not None: break
            print(f"  {YL}⚠ Bad JSON (attempt {attempt+1}/{MAX_JSON_RETRIES})…{R}")
            messages+=[{"role":"assistant","content":raw},
                       {"role":"user","content":RETRY_PROMPT}]
            spin=Spinner("Retrying").start()
            raw=call_model(messages,model,url,mode)
            spin.stop()
            parsed=parse_json(raw)

        if parsed is None:
            print(f"  {RD}Model could not produce valid JSON after {MAX_JSON_RETRIES} retries.{R}")
            consecutive_fails+=1
            if consecutive_fails>=3:
                print(f"  {RD}Too many consecutive failures. Stopping.{R}\n"); break
            continue
        consecutive_fails=0

        action=parsed.get("action","run")

        # ── DONE ─────────────────────────────────────────────────────────────
        if action=="done":
            hr(ch="═")
            print(f"  {GR}{B}✓  Task complete!{R}")
            if parsed.get("summary"):
                print(f"\n  {WH}{parsed['summary']}{R}")
            hr(ch="═"); print()
            return True

        # ── ASK ──────────────────────────────────────────────────────────────
        elif action=="ask":
            q=parsed.get("question","?")
            print(f"\n  {YL}❓ Agent asks:{R} {q}")
            ans=input(f"  {YL}   Your answer:{R} ").strip()
            messages+=[{"role":"assistant","content":raw},
                       {"role":"user","content":ans+"\n\nContinue task. JSON only."}]

        # ── RUN ──────────────────────────────────────────────────────────────
        else:
            cmd=parsed.get("command","").strip()
            reason=parsed.get("reason","")

            # print step header
            hr(w=62,ch="╌")
            print(f"  {MG}Step {step}{R}  {DIM}{reason}{R}")

            if not cmd:
                messages+=[{"role":"assistant","content":raw},
                           {"role":"user","content":
                            'Empty command field. Provide a command or use {"action":"done"}.'}]
                continue

            result=run_cmd(cmd)

            feedback=(
                f"Command: {cmd}\n"
                f"Exit code: {result['returncode']}\n"
                f"stdout:\n{result['stdout']}\n"
                f"stderr:\n{result['stderr']}\n\n"
                "Study the output above carefully.\n"
                "- If exit code is non-zero, the command FAILED — fix and retry.\n"
                "- If the task is now fully complete and verified, reply with "
                '{"action":"done","summary":"what was done"}.\n'
                "- Otherwise, run the next required command.\n"
                "Reply JSON only."
            )
            messages+=[{"role":"assistant","content":raw},
                       {"role":"user","content":feedback}]

    print(f"\n  {YL}Reached step limit ({MAX_ITERATIONS}).{R}\n")
    return False

# ─────────────────────────────────────────────────────────────────────────────
# Main menu
# ─────────────────────────────────────────────────────────────────────────────

def main_menu():
    while True:
        banner(); status_bar()
        print(f"  {B}{WH}Main Menu{R}"); hr()
        print(f"  {CY}1{R}. {B}▶  Run Task{R}         {DIM}auto-select model{R}")
        print(f"  {CY}2{R}. {B}⚙  Run Task{R}         {DIM}choose model manually{R}")
        print(f"  {CY}3{R}. {B}↓  Pull a Model{R}")
        print(f"  {CY}4{R}. {B}✓  System Check{R}")
        print(f"  {CY}5{R}. {B}⟳  Start Ollama{R}     {DIM}if stopped{R}")
        print(f"  {CY}0{R}. {DIM}Exit{R}"); hr()
        c=input(f"  {YL}Choice:{R} ").strip(); print()

        if c in ("1","2"):
            if not ensure_running(): input(f"  {DIM}Press Enter…{R}"); continue
            if c=="1":
                model=auto_model()
                if not model:
                    print(f"  {RD}No models installed. Use option 3 first.{R}\n")
                    input(f"  {DIM}Press Enter…{R}"); continue
                print(f"  {DIM}Auto-selected:{R} {CY}{model}{R}\n")
            else:
                banner(); models=_get_models()
                if not models:
                    print(f"  {RD}No models. Use option 3 first.{R}\n")
                    input(f"  {DIM}Press Enter…{R}"); continue
                model=pick("Select Model",[(m,m) for m in models])
                if not model: continue
                print()
            task=input(f"  {B}What do you want me to do?{R}\n  > ").strip()
            if not task: continue
            print(); run_agent(task,model)
            input(f"  {DIM}Press Enter to return to menu…{R}")

        elif c=="3":
            if not shutil.which("ollama"):
                print(f"  {RD}ollama not installed.{R}\n")
                input(f"  {DIM}Press Enter…{R}"); continue
            pull_menu()
        elif c=="4": system_check()
        elif c=="5": ensure_running(); input(f"\n  {DIM}Press Enter…{R}")
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
