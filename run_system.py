#!/usr/bin/env python3
"""
Interactive launcher with forceful port-killing and dynamic event loop.
Place in the project root (where s1, s2, ... reside).

Run: python launcher_interactive.py
"""
import os
import sys
import time
import shlex
import threading
import subprocess
import socket
from pathlib import Path

try:
    import psutil
except ImportError:
    print("[FATAL] psutil is required. pip install psutil")
    sys.exit(1)

# ----------------------------
# Config - adjust as needed
# ----------------------------
PORT_MAPPING = {
    "ms1": 8000, "ms2": 8001, "ms3": 8002, "ms4": 8003,
    "ms5": 8004, "ms6": None, "ms7": 8007, "ms8": 8008,
    "ms9": 8009, "ms10": 8010,
}
PROJECT_TYPE_MAPPING = {"ms8": "fastapi"}  # example override
COMMAND_EXCLUDE_LIST = ["generate_protos"]
GRPC_PORT_RANGE = list(range(50051, 50061))  # ports to check for gRPC commands

ALL_PORTS_TO_CLEAR = sorted(list(set([p for p in PORT_MAPPING.values() if p is not None] + GRPC_PORT_RANGE)))
MAX_RETRIES = 3
STARTUP_WAIT = 6
TERMINATION_WAIT = 2
LOG_DIR = Path.cwd() / "launcher_logs"
LOG_DIR.mkdir(exist_ok=True)

# Which management commands are critical and what ports we expect them to open
CRITICAL_MGMT_COMMANDS = {
    "run_grpc_server": {"ports": GRPC_PORT_RANGE, "name": "gRPC server"},
}

# Main entrypoint filenames to try when a service has no HTTP port (ms6 case)
MAIN_CANDIDATES = ["main.py", "app.py", "server.py", "run.py"]

# Global state: mapping service_name -> subprocess.Popen
RUNNING_PROCESSES = {}
RUNNING_LOCK = threading.Lock()
MONITOR_THREAD = None
SHOULD_MONITOR = True

# Windows console flag for create new console (optional)
CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)

# ----------------------------
# Helpers
# ----------------------------
def check_admin_privileges():
    try:
        is_admin = (os.getuid() == 0)
    except AttributeError:
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    if not is_admin:
        print("\n[FATAL] This script must be run as Administrator / root.\n")
        sys.exit(1)

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(('127.0.0.1', port)) == 0

def collect_pids_for_ports(ports):
    found = {}
    for conn in psutil.net_connections(kind='inet'):
        try:
            if conn.laddr and conn.laddr.port in ports and conn.status == psutil.CONN_LISTEN and conn.pid:
                found[conn.pid] = conn.laddr.port
        except Exception:
            pass
    return found

def force_kill_ports(ports, aggressive=True, wait_between=0.5, max_attempts=5):
    ports = sorted(set(ports))
    print(f"[ACTION] Attempting to free ports: {ports}")
    attempts = 0
    while attempts < max_attempts:
        pids = collect_pids_for_ports(ports)
        if not pids:
            print("  -> All requested ports are free.")
            return True

        print(f"  -> Found processes: {pids}  (attempt {attempts+1}/{max_attempts})")
        # polite terminate
        for pid, port in pids.items():
            try:
                proc = psutil.Process(pid)
                print(f"     - polite terminate PID {pid} ({proc.name()}) using port {port}")
                try:
                    proc.terminate()
                except Exception as e:
                    print(f"       [WARN] terminate failed: {e}")
            except psutil.NoSuchProcess:
                continue

        time.sleep(TERMINATION_WAIT)

        # force kill remaining
        pids = collect_pids_for_ports(ports)
        for pid, port in pids.items():
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    print(f"     - force kill PID {pid} ({proc.name()}) using port {port}")
                    try:
                        proc.kill()
                    except Exception as e:
                        print(f"       [WARN] kill failed: {e}")
                        if sys.platform == "win32":
                            try:
                                subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                print(f"       - taskkill fallback executed for PID {pid}")
                            except Exception:
                                pass
            except psutil.NoSuchProcess:
                continue

        time.sleep(wait_between)
        remaining = [p for p in ports if is_port_in_use(p)]
        if not remaining:
            print("  -> Ports cleared successfully.")
            return True

        print(f"  -> Still remaining ports after attempt {attempts+1}: {remaining}")
        attempts += 1

    if sys.platform == "win32":
        pids = collect_pids_for_ports(ports)
        for pid in list(pids.keys()):
            print(f"  -> FINAL-FORCE: taskkill /F /PID {pid}")
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False)
            except Exception:
                pass
        time.sleep(1)
    remaining = [p for p in ports if is_port_in_use(p)]
    if remaining:
        print(f"[ERROR] Stubborn ports remain: {remaining}")
        return False
    print("  -> Ports cleared successfully after final attempts.")
    return True

def find_python_executable(venv_path: Path):
    if sys.platform == "win32":
        candidates = [venv_path / "Scripts" / "python.exe", venv_path / "Scripts" / "python3.12.exe"]
    else:
        candidates = [venv_path / "bin" / "python", venv_path / "bin" / "python3.12"]
    for c in candidates:
        if c.exists():
            return str(c)
    return sys.executable

def make_child_env(python_exe_path: str):
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    env.setdefault('LANG', 'en_US.UTF-8')
    try:
        p = Path(python_exe_path).resolve()
        if p.parent.name.lower() in ("scripts", "bin"):
            venv_dir = p.parent.parent
            if venv_dir.exists():
                env['VIRTUAL_ENV'] = str(venv_dir)
                venv_bin = str(venv_dir / ("Scripts" if sys.platform == "win32" else "bin"))
                env_path = env.get('PATH', '')
                env['PATH'] = venv_bin + os.pathsep + env_path
    except Exception:
        pass
    return env

def write_log_header_bytes(logfile: Path, header: str):
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with open(logfile, "ab") as f:
        f.write(("\n\n==== " + header + " @ " + time.strftime('%Y-%m-%d %H:%M:%S') + " ====\n").encode("utf-8"))

# ----------------------------
# Process management (ms6-aware)
# ----------------------------
def start_service_process(service_name: str, ms_dir: Path, python_exe: str, port: int, project_type: str):
    """
    Start a service:
      - If port is provided: start server and verify port listen.
      - If port is None: try to find a main candidate and run it (verify process alive).
      - Else: skip server start but still run management commands later.
    """
    # If port configured -> behave like web server start + port verification
    if port is not None:
        if project_type == "django":
            args = [python_exe, "manage.py", "runserver", f"0.0.0.0:{port}"]
        elif project_type == "fastapi":
            args = [python_exe, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port), "--reload"]
        else:
            print(f"  [ERROR] Unknown project type: {project_type}")
            return False

        logpath = LOG_DIR / f"{service_name}__server.log"
        write_log_header_bytes(logpath, f"{service_name} server start (port {port})")
        env = make_child_env(python_exe)
        print(f"  -> Launching {service_name} with: {' '.join(args)} (cwd={ms_dir}) -> log: {logpath}")
        with open(logpath, "ab") as lf:
            try:
                creationflags = CREATE_NEW_CONSOLE if False and sys.platform == "win32" else 0
                proc = subprocess.Popen(args, cwd=ms_dir, env=env, stdout=lf, stderr=lf, shell=False, creationflags=creationflags)
            except Exception as e:
                print(f"  [ERROR] Failed to spawn process for {service_name}: {e}")
                return False

        for attempt in range(1, MAX_RETRIES + 1):
            time.sleep(STARTUP_WAIT)
            if proc.poll() is not None:
                print(f"  [ERROR] Service process for {service_name} exited early with returncode {proc.returncode}. See {logpath}")
                return False
            if is_port_in_use(port):
                with RUNNING_LOCK:
                    RUNNING_PROCESSES[service_name] = {"proc": proc, "type": "server", "port": port, "cwd": str(ms_dir), "log": str(logpath)}
                print(f"  [SUCCESS] {service_name} is listening on port {port} (pid {proc.pid}).")
                return True
            else:
                print(f"  [WAIT] {service_name} not listening yet (attempt {attempt}/{MAX_RETRIES})...")

        print(f"  [FATAL] {service_name} failed to bind on port {port} after {MAX_RETRIES} attempts. Terminating process.")
        try:
            proc.kill()
        except Exception:
            pass
        return False

    # If port is None -> try to find main candidates (ms6 scenario)
    for candidate in MAIN_CANDIDATES:
        candidate_path = ms_dir / candidate
        if candidate_path.exists():
            args = [python_exe, candidate]
            logpath = LOG_DIR / f"{service_name}__main.log"
            write_log_header_bytes(logpath, f"{service_name} main start -> {candidate}")
            env = make_child_env(python_exe)
            print(f"  -> Launching main for {service_name}: {' '.join(args)} (cwd={ms_dir}) -> log: {logpath}")
            with open(logpath, "ab") as lf:
                try:
                    proc = subprocess.Popen(args, cwd=ms_dir, env=env, stdout=lf, stderr=lf, shell=False)
                except Exception as e:
                    print(f"  [ERROR] Failed to spawn main process for {service_name}: {e}")
                    return False

            # Verify process is alive (cannot check port)
            for attempt in range(1, MAX_RETRIES + 1):
                time.sleep(STARTUP_WAIT)
                if proc.poll() is None:
                    with RUNNING_LOCK:
                        RUNNING_PROCESSES[service_name] = {"proc": proc, "type": "main", "cwd": str(ms_dir), "log": str(logpath)}
                    print(f"  [SUCCESS] {service_name} main started (pid {proc.pid}).")
                    return True
                else:
                    print(f"  [WAIT] {service_name} main not stable yet (attempt {attempt}/{MAX_RETRIES})...")

            print(f"  [FATAL] {service_name} main failed to stay alive after {MAX_RETRIES} attempts. See {logpath}")
            try:
                proc.kill()
            except Exception:
                pass
            return False

    # No port and no main -> nothing to start; return True so we continue to management commands
    print(f"  - No HTTP port and no main candidate for {service_name}. Skipping server/main start.")
    return True

def start_management_command(service_name: str, ms_dir: Path, python_exe: str, cmd_name: str, critical=False):
    args = [python_exe, "manage.py", cmd_name]
    logpath = LOG_DIR / f"{service_name}__{cmd_name}.log"
    write_log_header_bytes(logpath, f"{service_name} mgmt:{cmd_name}")
    env = make_child_env(python_exe)

    print(f"    -> Launching mgmt command: {' '.join(args)} (cwd={ms_dir}) -> log: {logpath}")
    with open(logpath, "ab") as lf:
        try:
            proc = subprocess.Popen(args, cwd=ms_dir, env=env, stdout=lf, stderr=lf, shell=False)
        except Exception as e:
            print(f"    [ERROR] Failed to start mgmt command {cmd_name}: {e}")
            return False

    if critical:
        expected_ports = CRITICAL_MGMT_COMMANDS.get(cmd_name, {}).get("ports", [])
        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            time.sleep(STARTUP_WAIT)
            if proc.poll() is not None:
                print(f"    [ERROR] Critical mgmt command {cmd_name} exited early (rc={proc.returncode}). See {logpath}")
                return False
            ok = any(is_port_in_use(p) for p in expected_ports)
            if ok:
                success = True
                break
            print(f"    [WAIT] mgmt '{cmd_name}' not listening yet (attempt {attempt}/{MAX_RETRIES})...")
        if not success:
            print(f"    [FATAL] Critical mgmt {cmd_name} failed to open expected ports. Killing process.")
            try:
                proc.kill()
            except Exception:
                pass
            return False

    with RUNNING_LOCK:
        RUNNING_PROCESSES[f"{service_name}::{cmd_name}"] = {"proc": proc, "type": "mgmt", "cwd": str(ms_dir), "log": str(logpath)}
    print(f"    [SUCCESS] mgmt command '{cmd_name}' running (pid {proc.pid}).")
    return True

# ----------------------------
# Higher-level flows
# ----------------------------
def start_all_services():
    root = Path.cwd()
    s_dirs = sorted([d for d in root.iterdir() if d.is_dir() and d.name.lower().startswith("s") and d.name[1:].isdigit()],
                    key=lambda p: int(''.join(filter(str.isdigit, p.name))))
    if not s_dirs:
        print("[ERROR] No s<n> directories found.")
        return False

    for s_dir in s_dirs:
        print("\n" + "="*10 + f" Processing {s_dir.name} " + "="*10)
        ms_entry = None
        for item in s_dir.iterdir():
            if item.is_dir() and item.name.lower().startswith("ms"):
                ms_entry = item
                break
        if not ms_entry:
            print("  - No msX folder inside this s<n> folder.")
            continue

        ms_name = ms_entry.name.lower()
        print(f"  -> Found microservice folder: {ms_entry.name}")
        python_exe = find_python_executable(s_dir)
        port = PORT_MAPPING.get(ms_name)
        project_type = PROJECT_TYPE_MAPPING.get(ms_name, "django")

        # Start server/main (now covers ms6 main)
        ok = start_service_process(ms_entry.name, ms_entry, python_exe, port, project_type)
        if not ok:
            print(f"[FATAL] Failed to start server/main for {ms_entry.name}. Aborting overall start.")
            return False

        # find management commands
        mgmt_files = sorted(ms_entry.rglob("management/commands/*.py"))
        launched = set()
        for f in mgmt_files:
            if f.name.startswith("_"):
                continue
            cmd = f.stem
            if cmd in launched or cmd in COMMAND_EXCLUDE_LIST:
                continue
            launched.add(cmd)
            critical = cmd in CRITICAL_MGMT_COMMANDS
            ok = start_management_command(ms_entry.name, ms_entry, python_exe, cmd, critical=critical)
            if not ok:
                print(f"[FATAL] Management command {cmd} for {ms_entry.name} failed. Aborting overall start.")
                return False

    print("\n[INFO] All requested services and management commands launched (or skipped).")
    return True

def stop_all_processes(graceful=True):
    print("[ACTION] Stopping all tracked processes...")
    with RUNNING_LOCK:
        items = list(RUNNING_PROCESSES.items())
    for name, info in items:
        proc = info.get("proc")
        try:
            if proc and proc.poll() is None:
                print(f"  - Terminating {name} (pid {proc.pid}) ...")
                try:
                    proc.terminate()
                except Exception:
                    pass
        except Exception:
            pass
    time.sleep(1)
    with RUNNING_LOCK:
        items = list(RUNNING_PROCESSES.items())
    for name, info in items:
        proc = info.get("proc")
        try:
            if proc and proc.poll() is None:
                print(f"  - Killing {name} (pid {proc.pid}) ...")
                try:
                    proc.kill()
                except Exception:
                    if sys.platform == "win32":
                        try:
                            subprocess.run(["taskkill", "/F", "/PID", str(proc.pid)], check=False)
                        except Exception:
                            pass
        except Exception:
            pass

    with RUNNING_LOCK:
        RUNNING_PROCESSES.clear()
    print("  -> All tracked processes stopped.")

# ----------------------------
# Monitoring thread
# ----------------------------
def monitor_loop():
    global SHOULD_MONITOR
    while SHOULD_MONITOR:
        with RUNNING_LOCK:
            items = list(RUNNING_PROCESSES.items())
        for name, info in items:
            proc = info.get("proc")
            try:
                if proc and proc.poll() is not None:
                    rc = proc.returncode
                    print(f"\n[MONITOR] Process '{name}' exited with code {rc}. See log: {info.get('log')}")
                    with RUNNING_LOCK:
                        RUNNING_PROCESSES.pop(name, None)
            except Exception:
                continue
        time.sleep(1)

# ----------------------------
# Interactive CLI (unchanged)
# ----------------------------
def print_help():
    print("""
Interactive launcher commands:
  start                - Clear ports and start all services + critical mgmt commands
  restart              - Kill all configured ports then start
  kill-ports           - Aggressively kill all configured ports immediately
  status               - Show tracked running processes and their ports
  list                 - List s<n> folders and ms inside
  stop <name>          - Stop tracked process or service (use name from status)
  run <shell-cmd>      - Run any shell command immediately (will not be monitored)
  tail <name|log>      - Tail a service log or open with less-like behavior (prints last 60 lines)
  exit                 - Stop all tracked processes and exit
  help                 - Show this message
""")

def cmd_list_services():
    root = Path.cwd()
    s_dirs = sorted([d for d in root.iterdir() if d.is_dir() and d.name.lower().startswith("s") and d.name[1:].isdigit()],
                    key=lambda p: int(''.join(filter(str.isdigit, p.name))))
    for s in s_dirs:
        print(f"- {s.name}")
        ms = [i.name for i in s.iterdir() if i.is_dir() and i.name.lower().startswith("ms")]
        for m in ms:
            print(f"    -> {m} (port {PORT_MAPPING.get(m.lower())})")

def cmd_status():
    with RUNNING_LOCK:
        if not RUNNING_PROCESSES:
            print("No processes tracked as running.")
            return
        for name, info in RUNNING_PROCESSES.items():
            proc = info.get("proc")
            typ = info.get("type")
            port = info.get("port", "")
            pid = proc.pid if proc else "(no-pid)"
            print(f"{name:35} | pid={pid:<6} | type={typ:<6} | port={port:<5} | log={info.get('log')}")

def cmd_tail(name_or_log):
    candidates = list(LOG_DIR.glob(f"*{name_or_log}*.log"))
    if not candidates:
        print("No log file matches that name.")
        return
    p = candidates[0]
    print(f"--- Last 60 lines of {p} ---")
    try:
        with open(p, "r", encoding="utf-8") as f:
            lines = f.readlines()[-60:]
            print("".join(lines))
    except Exception as e:
        print("Failed to read log:", e)

def cmd_run_shell(cmd_str):
    print(f"[RUN] Executing: {cmd_str}")
    try:
        subprocess.run(cmd_str, shell=True, check=False)
    except Exception as e:
        print("Run failed:", e)

def interactive_loop():
    global SHOULD_MONITOR, MONITOR_THREAD
    print("Interactive launcher started. Type 'help' for commands.")
    MONITOR_THREAD = threading.Thread(target=monitor_loop, daemon=True)
    MONITOR_THREAD.start()

    try:
        while True:
            raw = input("launcher> ").strip()
            if not raw:
                continue
            parts = shlex.split(raw)
            cmd = parts[0].lower()
            args = parts[1:]

            if cmd == "help":
                print_help()
            elif cmd == "start":
                clear_ok = force_kill_ports(ALL_PORTS_TO_CLEAR)
                if not clear_ok:
                    print("[ERROR] Could not clear ports. Aborting start.")
                    continue
                ok = start_all_services()
                print("[RESULT] start returned:", ok)
            elif cmd == "restart":
                ok = force_kill_ports(ALL_PORTS_TO_CLEAR)
                if not ok:
                    print("[ERROR] Could not clear ports for restart.")
                    continue
                stop_all_processes()
                time.sleep(1)
                ok = start_all_services()
                print("[RESULT] restart returned:", ok)
            elif cmd in ("kill-ports", "kill_ports", "kill"):
                ok = force_kill_ports(ALL_PORTS_TO_CLEAR)
                print("[RESULT] kill-ports returned:", ok)
            elif cmd == "status":
                cmd_status()
            elif cmd == "list":
                cmd_list_services()
            elif cmd == "stop":
                if not args:
                    print("Usage: stop <name>")
                    continue
                name = args[0]
                with RUNNING_LOCK:
                    item = RUNNING_PROCESSES.get(name)
                if not item:
                    print("No tracked process by that name.")
                    continue
                proc = item.get("proc")
                print(f"Stopping {name} (pid {proc.pid})")
                try:
                    proc.terminate()
                except Exception:
                    pass
                time.sleep(1)
                try:
                    if proc.poll() is None:
                        proc.kill()
                except Exception:
                    pass
                with RUNNING_LOCK:
                    RUNNING_PROCESSES.pop(name, None)
            elif cmd == "run":
                if not args:
                    print("Usage: run <command>")
                    continue
                cmd_run_shell(" ".join(args))
            elif cmd == "tail":
                if not args:
                    print("Usage: tail <service-or-log-name>")
                    continue
                cmd_tail(args[0])
            elif cmd == "exit":
                print("Exiting: stopping all processes first...")
                SHOULD_MONITOR = False
                stop_all_processes()
                force_kill_ports(ALL_PORTS_TO_CLEAR)
                print("Goodbye.")
                break
            else:
                print("Unknown command. Type 'help'.")
    except (KeyboardInterrupt, EOFError):
        print("\nCaught interrupt — exiting and stopping processes.")
        SHOULD_MONITOR = False
        stop_all_processes()
        force_kill_ports(ALL_PORTS_TO_CLEAR)
        sys.exit(0)

# ----------------------------
# Entrypoint
# ----------------------------
if __name__ == "__main__":
    check_admin_privileges()
    print("======================================================")
    print("=      INTERACTIVE LAUNCHER (FORCE PORT KILL)       =")
    print("======================================================")
    print(f"Configured ports to clear: {ALL_PORTS_TO_CLEAR}")
    print(f"Logs: {LOG_DIR}")
    interactive_loop()
