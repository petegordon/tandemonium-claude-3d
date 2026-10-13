"""Run comfy_job.py jobs one at a time, each on a FRESH ComfyUI (:8189), with a RAM guard.

  .venv python scripts/comfy_batch.py pixal-mv --chars outfit_male_victorian/boots[,set/garment...] --seed 42 \
      [--min-ram 18] [--keep-server] [-- <extra comfy_job.py args>]

Why: one long-lived ComfyUI grew in system RAM across an 8-garment loop until Claude Code's low-memory reaper
killed it (2026-10-12, during the boots). Per job:
1. refuse if system free RAM < --min-ram GB (other apps holding memory);
2. start ComfyUI (the RESUME.md command; log -> ComfyUI-claude/comfy-8189.log), wait for /system_stats;
3. run comfy_job.py as a child, sampling every 2 s: ComfyUI's resident memory (process + children) and system free RAM;
4. stop ComfyUI (terminate the process tree) so all of its RAM comes back before the next job.
Each job's peaks go to out/comfy_batch.jsonl. Never touches :8000. Run it in the foreground (one or two jobs per call):
background shells are reaped under memory pressure while the session is idle.
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
COMFY = Path(r"C:\Users\pete\ComfyUI-claude")
PY = COMFY / ".venv" / "Scripts" / "python.exe"
SERVER = "http://127.0.0.1:8189"
argv = sys.argv[1:]
extra = argv[argv.index("--") + 1:] if "--" in argv else []
argv = argv[:argv.index("--")] if "--" in argv else argv
CMD = argv[0]


def opt(name, default):
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


CHARS = opt("--chars", "").split(",")
SEED = opt("--seed", 42)
MIN_RAM = opt("--min-ram", 18.0)   # one Pixal3D job peaks ~15.4 GB in ComfyUI (boots: free 19.8 -> 4.0 GB)
KEEP = "--keep-server" in argv
GB = 1024 ** 3


def free_gb():
    return psutil.virtual_memory().available / GB


def up():
    try:
        urllib.request.urlopen(SERVER + "/system_stats", timeout=3).read()
        return True
    except Exception:
        return False


def rss_tree(p):
    try:
        procs = [p] + p.children(recursive=True)
        return sum(q.memory_info().rss for q in procs if q.is_running()) / GB
    except psutil.Error:
        return 0.0


def start():
    if up():
        sys.exit("ABORT: something already answers on :8189; stop it first (this runner owns a fresh server per job)")
    log = open(COMFY / "comfy-8189.log", "w", encoding="utf-8")
    p = subprocess.Popen([str(PY), "main.py", "--listen", "127.0.0.1", "--port", "8189",
                          "--extra-model-paths-config", "extra_model_paths.yaml", "--disable-pinned-memory",
                          "--cache-none"], cwd=COMFY, stdout=log, stderr=subprocess.STDOUT)
    for _ in range(120):
        if up():
            return p
        if p.poll() is not None:
            sys.exit(f"ABORT: ComfyUI exited during start (code {p.returncode}); see comfy-8189.log")
        time.sleep(2)
    stop(p)
    sys.exit("ABORT: ComfyUI did not answer within 4 min")


def stop(p):
    try:
        ps = psutil.Process(p.pid)
        kids = ps.children(recursive=True)
        for q in kids + [ps]:
            q.terminate()
        psutil.wait_procs(kids + [ps], timeout=20)
        for q in kids + [ps]:
            if q.is_running():
                q.kill()
    except psutil.NoSuchProcess:
        pass


results = []
for char in CHARS:
    f0 = free_gb()
    if f0 < MIN_RAM:
        print(f"SKIP {char}: only {f0:.1f} GB RAM free (< {MIN_RAM}); close other apps", flush=True)
        results.append({"char": char, "skipped": f"ram {f0:.1f} GB"})
        continue
    t0 = time.time()
    srv = start()
    sp = psutil.Process(srv.pid)
    job = subprocess.Popen([str(PY), str(ROOT / "scripts" / "comfy_job.py"), CMD, "--char", char,
                            "--seed", str(SEED)] + extra, cwd=ROOT, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    peak_rss, low_free, out = 0.0, f0, []
    while job.poll() is None:
        peak_rss = max(peak_rss, rss_tree(sp))
        low_free = min(low_free, free_gb())
        time.sleep(2)
    out = job.stdout.read()
    if not KEEP:
        stop(srv)
    ok = job.returncode == 0
    entry = {"char": char, "cmd": CMD, "seed": SEED, "ok": ok, "secs": round(time.time() - t0),
             "comfy_peak_rss_gb": round(peak_rss, 1), "sys_free_gb_start": round(f0, 1),
             "sys_free_gb_low": round(low_free, 1), "sys_free_gb_after": round(free_gb(), 1),
             "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(ROOT / "out" / "comfy_batch.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    print("JOB", json.dumps(entry), flush=True)
    if not ok:
        print(out[-2000:], flush=True)
    results.append(entry)
print("BATCH", json.dumps(results))
