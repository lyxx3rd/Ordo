"""Explicit lifecycle CLI. No processes are started by import or installation."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import secrets
import socket
import subprocess
import sys
import time

from .config import load


def identity(pid):
    try:
        # Linux proc start time protects against PID reuse.
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if stat[0] == "Z":
            return None
        return stat[19]
    except (OSError, IndexError):
        return None


def alive(record):
    if not record:
        return False
    current = identity(record["pid"])
    return current is not None and current == record["start_time"]


def stop(record):
    if not alive(record):
        return
    pid = record["pid"]
    if os.getpgid(pid) != pid:
        raise RuntimeError("Refusing to stop a process without its own recorded process group")
    os.killpg(pid, signal.SIGTERM)
    deadline = time.monotonic() + 30
    while alive(record) and time.monotonic() < deadline:
        time.sleep(0.2)
    if alive(record):
        os.killpg(pid, signal.SIGKILL)


def main():
    ap = argparse.ArgumentParser(description="Start/stop/status the two Ordo services (Linux)")
    ap.add_argument("action", choices=["start", "stop", "status", "check", "init-token", "restart-api"])
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    config_path = args.config.expanduser().resolve()
    cfg = load(config_path)
    runtime = Path(cfg.runtime_dir)
    runtime.mkdir(parents=True, exist_ok=True)
    token_file = runtime / "api_token.txt"
    if args.action == "init-token":
        # Runtime credential, never print the value or put it in command arguments.
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_urlsafe(32) + "\n")
        print(f"Token created (0600): {token_file}")
        return
    if cfg.auth_enabled and not os.environ.get("ORDO_API_TOKEN") and token_file.exists():
        if token_file.stat().st_mode & 0o077:
            raise RuntimeError("api_token.txt must have owner-only permissions (chmod 600)")
        os.environ["ORDO_API_TOKEN"] = token_file.read_text().strip()
    with (runtime / "manager.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state_path = runtime / "processes.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if args.action == "status":
            print(json.dumps({name: {"pid": state.get(name, {}).get("pid"), "alive": bool(alive(state.get(name)))}
                              for name in ("model", "api")}, indent=2))
            return
        if args.action == "stop":
            for name in ("api", "model"):
                stop(state.get(name))
            print("Stopped only recorded service processes; model files and logs retained.")
            return
        if cfg.auth_enabled and cfg.api_host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("ORDO_API_TOKEN"):
            raise RuntimeError("External binding requires ORDO_API_TOKEN")
        if args.action == "restart-api":
            if not alive(state.get("model")):
                raise RuntimeError("Recorded model must still be running for restart-api")
            stop(state.get("api"))
            env = dict(os.environ, ORDO_CONFIG=str(config_path), PYTHONUNBUFFERED="1")
            env['PYTHONPATH'] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get('PYTHONPATH', '')
            cmd = [sys.executable, '-u', '-m', 'uvicorn', 'ordo_local.app:create_app', '--factory',
                   '--host', cfg.api_host, '--port', str(cfg.api_port), '--workers', '1', '--log-level', 'info']
            with (runtime/'api.log').open('ab', buffering=0) as log:
                child = subprocess.Popen(cmd, env=env, stdin=subprocess.DEVNULL, stdout=log,
                                         stderr=subprocess.STDOUT, start_new_session=True)
            state['api'] = {'pid':child.pid, 'start_time':identity(child.pid)}
            state_path.write_text(json.dumps(state,indent=2)+'\n')
            print('Restarted only API; model process retained. Check /ready.')
            return
        if any(alive(state.get(n)) for n in ("api", "model")):
            raise RuntimeError("Recorded service still running. Use status/stop; no service was replaced.")
        base = Path(cfg.model_path)
        if not (base / "config.json").is_file():
            raise RuntimeError("model_path must point to the final merged model directory")
        if cfg.model_port == cfg.api_port:
            raise RuntimeError("Model/API must use distinct ports")
        # The managed pair is local. An externally managed model may be used by
        # launching uvicorn separately, rather than accidentally spawning two models.
        expected = f"http://127.0.0.1:{cfg.model_port}/v1"
        if cfg.model_url.rstrip("/") != expected:
            raise RuntimeError(f"Managed model_url must be {expected}")
        model_python = shutil.which(cfg.model_python)
        if not model_python:
            raise RuntimeError("model_python executable not found")
        subprocess.run([model_python, "-c", "import vllm"], check=True)
        model_cmd = [model_python, "-u", "-m", "vllm.entrypoints.cli.main", "serve", str(base),
                     "--host", "127.0.0.1", "--port", str(cfg.model_port), "--served-model-name", cfg.model_name,
                     "--dtype", "bfloat16", "--max-model-len", str(cfg.max_model_len),
                     "--gpu-memory-utilization", str(cfg.gpu_memory_utilization),
                     "--max-num-seqs", str(cfg.concurrency), "--enable-prefix-caching", "--generation-config", "vllm"]
        api_cmd = [sys.executable, "-u", "-m", "uvicorn", "ordo_local.app:create_app", "--factory",
                   "--host", cfg.api_host, "--port", str(cfg.api_port), "--workers", "1", "--log-level", "info"]
        for host, port in [("127.0.0.1", cfg.model_port), (cfg.api_host, cfg.api_port)]:
            family = socket.AF_INET6 if ":" in host else socket.AF_INET
            with socket.socket(family) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))
        if args.action == "check":
            print(json.dumps({"model_command": model_cmd, "api_command": api_cmd,
                              "note": "Preflight only; GPU memory fit is not tested; no server started."}, indent=2))
            return
        state = {}
        env = dict(os.environ, ORDO_CONFIG=str(config_path), PYTHONUNBUFFERED="1", TOKENIZERS_PARALLELISM="false")
        # Permit running from a source checkout as well as an installed package.
        package_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = package_root + os.pathsep + env.get("PYTHONPATH", "")
        env.pop("WEB_CONCURRENCY", None)
        try:
            for name, command in [("model", model_cmd), ("api", api_cmd)]:
                child_env = dict(env)
                if name == "model":
                    child_env["CUDA_VISIBLE_DEVICES"] = cfg.gpu
                with (runtime / f"{name}.log").open("ab", buffering=0) as log:
                    child = subprocess.Popen(command, env=child_env, stdin=subprocess.DEVNULL,
                                             stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                state[name] = {"pid": child.pid, "start_time": identity(child.pid)}
                state_path.write_text(json.dumps(state, indent=2) + "\n")
                time.sleep(0.2)
                if child.poll() is not None:
                    raise RuntimeError(f"{name} exited; inspect {runtime / (name + '.log')}")
        except BaseException:
            for record in state.values():
                stop(record)
            raise
        print(f"Started background processes. API may return 503 until model is ready.\nLOGS={runtime}\n"
              f"READY=http://127.0.0.1:{cfg.api_port}/ready")


if __name__ == "__main__":
    main()
