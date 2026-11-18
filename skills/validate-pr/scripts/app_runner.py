#!/usr/bin/env python3
"""Run the application's setup steps, start it, check it answers, and stop it, logging everything into the run folder.

  step   run one setup command (install, build, migrate) with a timeout; output -> logs/setup-<name>.log
  start  launch the app in its own process group; output -> logs/app-<name>.log; poll --url until it answers.
         Exit 0 when ready. Exit 3 (BLOCKED) when the port is already taken, the process exits, or it never answers:
         the process is stopped and the blocker (reason, exit code, log tail) is written to metadata.json app.blocker.
  stop   stop the process group (SIGTERM, then SIGKILL) and record it. Safe to call more than once.
  stop-all  stop every process this run started (use in cleanup, even after failures).

Secrets the skill never needs (GitHub, cloud and AI tokens) are removed from the environment of everything launched.
Variables the app needs can be given with --env KEY=VALUE or --env-file (values are never written to the run folder).

Usage:
  app_runner.py step  --run D --cwd W --name install [--timeout 900] -- npm ci
  app_runner.py start --run D --cwd W --name web --url http://127.0.0.1:3000 [--timeout 180] [--env K=V] [--env-file F] -- npm run start
  app_runner.py stop  --run D --name web
  app_runner.py stop-all --run D

Exit codes: 0 ok, 1 step failed, 2 usage error, 3 app blocked (not reachable).
"""
import argparse, json, os, signal, socket, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import clean_env, load_meta, log_event, merge_meta, now, out, rel, run_dir  # noqa: E402

POSIX = os.name == "posix"


def tail(p, n=40):
    try:
        return "\n".join(Path(p).read_text(encoding="utf-8", errors="replace").splitlines()[-n:])
    except OSError:
        return ""


def env_from(a):
    extra = {}
    if a.env_file:
        for ln in Path(a.env_file).expanduser().read_text(encoding="utf-8").splitlines():
            ln = ln.strip()
            if ln and not ln.startswith("#") and "=" in ln:
                k, v = (ln[7:] if ln.startswith("export ") else ln).split("=", 1)
                extra[k.strip()] = v.strip().strip("\"'")
    for kv in a.env or []:
        k, _, v = kv.partition("=")
        extra[k] = v
    return clean_env(extra), sorted(extra)


def command(a):
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    if not cmd:
        raise SystemExit(json.dumps({"error": "give the command after --"}))
    # One string -> run through the shell (documented commands often use &&, env assignments, etc.)
    return (cmd[0], True) if len(cmd) == 1 else (cmd, False)


def port_open(host, port):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def answers(url):
    """Any HTTP response below 500 means the app is serving (a 401/404 at / is still an app that is up)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "validate-pr"}), timeout=3) as r:
            return r.status, None
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception as e:  # noqa: BLE001  connection refused, reset, timeout
        return None, f"{type(e).__name__}: {e}"


def procs(d):
    p = Path(d) / "logs" / "processes.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def save_procs(d, data):
    (Path(d) / "logs" / "processes.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def kill_group(pid):
    """Terminate the whole process group (npm -> node -> workers), then force it."""
    def alive():
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False
    if not alive():
        return "already exited"
    try:
        if POSIX:
            os.killpg(pid, signal.SIGTERM)
        else:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    except ProcessLookupError:
        return "already exited"
    for _ in range(50):
        if not alive():
            return "terminated"
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
        time.sleep(0.2)
    if POSIX:
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return "killed"


def cmd_step(a):
    d = run_dir(a.run)
    cmd, shell = command(a)
    env, keys = env_from(a)
    log = d / "logs" / f"setup-{a.name}.log"
    t0 = time.time()
    with log.open("w", encoding="utf-8") as f:
        f.write(f"# {now()}  cwd={a.cwd}\n# $ {cmd if shell else ' '.join(cmd)}\n\n")
        f.flush()
        try:
            code = subprocess.run(cmd, shell=shell, cwd=a.cwd, env=env, stdout=f, stderr=subprocess.STDOUT, timeout=a.timeout).returncode
            reason = None if code == 0 else f"exit code {code}"
        except subprocess.TimeoutExpired:
            code, reason = 124, f"timed out after {a.timeout}s"
        except FileNotFoundError as e:
            code, reason = 127, f"command not found: {e.filename}"
    step = {"name": a.name, "cmd": cmd if shell else " ".join(cmd), "cwd": a.cwd, "exit_code": code, "ok": code == 0,
            "seconds": round(time.time() - t0, 1), "log": rel(d, log), "env_keys": keys, "reason": reason}
    meta = load_meta(d)
    steps = [s for s in meta.get("app", {}).get("setup_steps", []) if s["name"] != a.name] + [step]
    merge_meta(d, {"app": {"setup_steps": steps}})
    log_event(d, {"event": "setup_step", **{k: step[k] for k in ("name", "exit_code", "seconds")}})
    if code != 0:
        step["log_tail"] = tail(log)
    return out(step, 0 if code == 0 else 1)


def blocked(d, a, reason, log, pid=None, code=None):
    if pid:
        kill_group(pid)
        p = procs(d); p.pop(a.name, None); save_procs(d, p)
    b = {"name": a.name, "reason": reason, "exit_code": code, "url": a.url, "log": rel(d, log), "log_tail": tail(log), "at": now()}
    merge_meta(d, {"app": {"ready": False, "blocker": b}})
    log_event(d, {"event": "app_blocked", "name": a.name, "reason": reason})
    return out({"status": "BLOCKED", **b}, 3)


def cmd_start(a):
    d = run_dir(a.run)
    cmd, shell = command(a)
    env, keys = env_from(a)
    u = urlparse(a.url)
    host, port = u.hostname or "127.0.0.1", u.port or (443 if u.scheme == "https" else 80)
    log = d / "logs" / f"app-{a.name}.log"
    if port_open(host, port):
        log.write_text(f"# {now()} not started: {host}:{port} was already in use before launch\n", encoding="utf-8")
        return blocked(d, a, f"port {port} is already in use by another process; tests would hit the wrong app. "
                             f"Stop it or start this app on another port.", log)
    env.setdefault("PORT", str(port))
    env.setdefault("CI", "1")
    f = log.open("w", encoding="utf-8")
    f.write(f"# {now()}  cwd={a.cwd}\n# $ {cmd if shell else ' '.join(cmd)}\n\n")
    f.flush()
    kw = {"start_new_session": True} if POSIX else {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    try:
        p = subprocess.Popen(cmd, shell=shell, cwd=a.cwd, env=env, stdout=f, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kw)
    except FileNotFoundError as e:
        return blocked(d, a, f"command not found: {e.filename}", log, code=127)
    data = procs(d)
    data[a.name] = {"pid": p.pid, "cmd": cmd if shell else " ".join(cmd), "cwd": a.cwd, "url": a.url, "started_at": now()}
    save_procs(d, data)
    t0, last_err, status = time.time(), None, None
    while time.time() - t0 < a.timeout:
        if (code := p.poll()) is not None:
            return blocked(d, a, f"the app process exited with code {code} before it answered at {a.url}", log, code=code)
        status, last_err = answers(a.url)
        if status is not None and status < 500:
            break
        time.sleep(1)
    else:
        return blocked(d, a, f"no answer below HTTP 500 at {a.url} within {a.timeout}s (last: {status or last_err})", log, pid=p.pid)
    secs = round(time.time() - t0, 1)
    merge_meta(d, {"app": {"ready": True, "blocker": None, "name": a.name, "url": a.url, "launch_command": data[a.name]["cmd"],
                           "cwd": a.cwd, "startup_seconds": secs, "ready_http_status": status, "log": rel(d, log), "env_keys": keys}})
    log_event(d, {"event": "app_ready", "name": a.name, "url": a.url, "startup_seconds": secs, "http_status": status})
    return out({"status": "READY", "url": a.url, "pid": p.pid, "startup_seconds": secs, "http_status": status, "log": str(log)})


def cmd_stop(a, names=None):
    d = run_dir(a.run)
    data = procs(d)
    names = names if names is not None else [a.name]
    res = {}
    for n in names:
        if n in data:
            res[n] = kill_group(data[n]["pid"])
            data.pop(n)
            log_event(d, {"event": "app_stopped", "name": n, "result": res[n]})
        else:
            res[n] = "not running (nothing recorded)"
    save_procs(d, data)
    merge_meta(d, {"app": {"stopped_at": now()}})
    return out({"stopped": res})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="action", required=True)
    for name in ("step", "start"):
        p = sub.add_parser(name)
        p.add_argument("--run", required=True); p.add_argument("--cwd", required=True); p.add_argument("--name", required=True)
        p.add_argument("--timeout", type=int, default=900 if name == "step" else 180)
        p.add_argument("--env", action="append"); p.add_argument("--env-file")
        if name == "start":
            p.add_argument("--url", required=True)
        p.add_argument("cmd", nargs=argparse.REMAINDER)
    p = sub.add_parser("stop"); p.add_argument("--run", required=True); p.add_argument("--name", required=True)
    sub.add_parser("stop-all").add_argument("--run", required=True)
    a = ap.parse_args()
    if a.action == "step":
        return cmd_step(a)
    if a.action == "start":
        return cmd_start(a)
    if a.action == "stop":
        return cmd_stop(a)
    return cmd_stop(a, list(procs(run_dir(a.run))))


if __name__ == "__main__":
    sys.exit(main())
