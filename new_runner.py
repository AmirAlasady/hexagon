#!/usr/bin/env python3
"""
new_runner_full.py - Full corrected orchestrator with GUI, Docker, port-killer, ms6 support.

Save in project root (where s1, s2, ... reside) and run:
    python3.12 new_runner_full.py

Notes:
 - Sound disabled by default. Enable with environment variable ENABLE_SOUNDS=1.
 - Requires: PySide6, psutil.
"""
import os
os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.ffmpeg=false")  # reduce FFmpeg spam in Qt logs
import sys
import time
import threading
import subprocess
import queue
import venv
import logging
import functools
import re
import shutil
from dataclasses import dataclass, field
from typing import Dict, Optional, List, Set
from pathlib import Path
import socket

# Qt GUI
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTextEdit, QTabWidget, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QHeaderView, QStackedWidget
)
from PySide6.QtCore import QTimer, Qt, Signal, QObject, QUrl
from PySide6.QtGui import QFont, QColor, QCloseEvent

# Monitoring
import psutil

# ----------------------------
# Configuration (edit as needed)
# ----------------------------
PORT_MAPPING = {
    "ms1": 8000, "ms2": 8001, "ms3": 8002, "ms4": 8003,
    "ms5": 8004, "ms6": None, "ms7": 8007, "ms8": 8008,
    "ms9": 8009, "ms10": 8010,
}
PROJECT_TYPE_MAPPING = {"ms8": "fastapi"}
COMMAND_EXCLUDE_LIST = ["generate_protos"]
GRPC_PORT_RANGE = list(range(50051, 50061))
MAIN_CANDIDATES = ["main.py", "app.py", "server.py", "run.py"]

ALL_PORTS_TO_CLEAR = sorted(list(set([p for p in PORT_MAPPING.values() if p is not None] + GRPC_PORT_RANGE)))
MAX_RETRIES = 3
STARTUP_WAIT = 6
TERMINATION_WAIT = 1
LOG_DIR = Path.cwd() / "launcher_logs"
LOG_DIR.mkdir(exist_ok=True)

# Critical mgmt commands expecting ports
CRITICAL_MGMT_COMMANDS = {
    "run_grpc_server": {"ports": GRPC_PORT_RANGE, "name": "gRPC server"},
}

# Windows flags
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)

# ----------------------------
# Utilities
# ----------------------------
def natural_sort_key(s: str):
    return [int(text) if text.isdigit() else text.lower() for text in re.split('([0-9]+)', s)]

def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(('127.0.0.1', port)) == 0

def collect_pids_for_ports(ports: List[int]) -> Dict[int,int]:
    found = {}
    for conn in psutil.net_connections(kind='inet'):
        try:
            if conn.laddr and conn.laddr.port in ports and conn.status == psutil.CONN_LISTEN and conn.pid:
                found[conn.pid] = conn.laddr.port
        except Exception:
            pass
    return found

def force_kill_ports(ports: List[int], max_attempts: int = 5, wait_between: float = 0.5) -> bool:
    ports = sorted(set([p for p in ports if p is not None]))
    logging.getLogger().action(f"Attempting to free ports: {ports}")
    attempts = 0
    while attempts < max_attempts:
        pids = collect_pids_for_ports(ports)
        if not pids:
            logging.getLogger().info("Ports are free.")
            return True
        logging.getLogger().warning(f"Found processes holding ports: {pids} (attempt {attempts+1}/{max_attempts})")
        for pid, port in pids.items():
            try:
                proc = psutil.Process(pid)
                logging.getLogger().info(f"Terminating PID {pid} ({proc.name()}) on port {port}")
                try:
                    proc.terminate()
                except Exception as e:
                    logging.getLogger().warning(f"terminate failed: {e}")
            except psutil.NoSuchProcess:
                pass
        time.sleep(TERMINATION_WAIT)
        # re-collect, force kill
        pids = collect_pids_for_ports(ports)
        for pid, port in pids.items():
            try:
                proc = psutil.Process(pid)
                if proc.is_running():
                    logging.getLogger().warning(f"Killing PID {pid} ({proc.name()}) on port {port}")
                    try:
                        proc.kill()
                    except Exception as e:
                        logging.getLogger().warning(f"kill failed: {e}")
                        if sys.platform == "win32":
                            try:
                                subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                logging.getLogger().info("taskkill fallback executed")
                            except Exception:
                                pass
            except psutil.NoSuchProcess:
                pass
        time.sleep(wait_between)
        remaining = [p for p in ports if is_port_in_use(p)]
        if not remaining:
            logging.getLogger().info("Ports cleared successfully.")
            return True
        logging.getLogger().warning(f"Still remaining ports: {remaining}")
        attempts += 1
    # final fallback on Windows
    if sys.platform == "win32":
        pids = collect_pids_for_ports(ports)
        for pid in list(pids.keys()):
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], check=False)
            except Exception:
                pass
        time.sleep(1)
    remaining = [p for p in ports if is_port_in_use(p)]
    if remaining:
        logging.getLogger().error(f"Stubborn ports remain: {remaining}")
        return False
    logging.getLogger().info("Ports cleared after final attempts.")
    return True

def find_python_executable(s_dir: Path) -> str:
    if sys.platform == "win32":
        candidates = [s_dir / "Scripts" / "python.exe", s_dir / "Scripts" / "python3.12.exe"]
    else:
        candidates = [s_dir / "bin" / "python", s_dir / "bin" / "python3.12"]
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
                env['PATH'] = venv_bin + os.pathsep + env.get('PATH', '')
    except Exception:
        pass
    return env

def write_log_header_bytes(logfile: Path, header: str):
    logfile.parent.mkdir(parents=True, exist_ok=True)
    with open(logfile, "ab") as f:
        f.write(("\n\n==== " + header + " @ " + time.strftime('%Y-%m-%d %H:%M:%S') + " ====\n").encode("utf-8"))

def _find_compose_file(root_path: str) -> Optional[str]:
    candidates = [
        "docker-compose.yml", "docker-compose.yaml",
        "compose.yml", "compose.yaml"
    ]
    for name in candidates:
        p = os.path.join(root_path, name)
        if os.path.exists(p):
            return p
    return None

def _get_docker_cmd() -> List[str]:
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    if shutil.which("docker"):
        return ["docker", "compose"]
    return ["docker", "compose"]

# ----------------------------
# Data structures
# ----------------------------
@dataclass
class ServiceInfo:
    unique_id: str
    display_name: str
    project_name: str
    project_path: str
    command: List[str]
    python_exe: str = sys.executable
    process: Optional[subprocess.Popen] = None
    log_queue: queue.Queue = field(default_factory=queue.Queue)
    pid: Optional[int] = None
    status: str = 'stopped'
    tree_item: Optional[QTreeWidgetItem] = None
    control_buttons: Dict[str, QPushButton] = field(default_factory=dict)
    port: Optional[int] = None
    project_type: str = "django"

# ----------------------------
# Logging -> GUI helper
# ----------------------------
class QtLogHandler(logging.Handler):
    def __init__(self, log_emitter): super().__init__(); self.log_emitter = log_emitter
    def emit(self, record):
        try:
            self.log_emitter.append_html.emit(self.format(record))
        except Exception:
            pass

class LogEmitter(QObject):
    append_html = Signal(str)

class ColoredFormatter(logging.Formatter):
    COLORS = {'WARNING': 'orange', 'INFO': '#aaffaa', 'DEBUG': 'cyan', 'CRITICAL': 'red', 'ERROR': 'red', 'ACTION': '#87CEEB'}
    def format(self, record):
        msg = super().format(record)
        color = self.COLORS.get(record.levelname, 'white')
        return f'<pre style="margin:0;padding:0;"><font color="{color}">{msg}</font></pre>'

class StreamToLogger:
    def __init__(self, logger, level): self.logger = logger; self.level = level
    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.level, line.rstrip())
    def flush(self): pass

# ----------------------------
# Project scanner
# ----------------------------
class ProjectScanner:
    def __init__(self, root: str):
        self.root = Path(root)

    def scan(self) -> Dict[str, ServiceInfo]:
        services: Dict[str, ServiceInfo] = {}
        s_dirs = sorted([d for d in self.root.iterdir() if d.is_dir() and re.match(r'^s\d+$', d.name)], key=lambda x: int(re.search(r'\d+', x.name).group()))
        for s_dir in s_dirs:
            # find ms directory inside s_dir
            ms_dir = next((item for item in s_dir.iterdir() if item.is_dir() and item.name.lower().startswith('ms')), None)
            if not ms_dir:
                continue
            ms_name = ms_dir.name.lower()
            python_exe = find_python_executable(s_dir)
            port = PORT_MAPPING.get(ms_name)
            project_type = PROJECT_TYPE_MAPPING.get(ms_name, "django")
            if port is not None:
                if project_type == "django":
                    cmd = ["manage.py", "runserver", f"0.0.0.0:{port}"]
                else:
                    cmd = ["-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port), "--reload"]
                sid = f"{ms_dir.name}-server"
                services[sid] = ServiceInfo(sid, "runserver" if project_type == "django" else "uvicorn", ms_dir.name, str(ms_dir), cmd, python_exe, port=port, project_type=project_type)
            else:
                for candidate in MAIN_CANDIDATES:
                    if (ms_dir / candidate).exists():
                        sid = f"{ms_dir.name}-main"
                        services[sid] = ServiceInfo(sid, "main", ms_dir.name, str(ms_dir), [candidate], python_exe, port=None, project_type="main")
                        break
            # find management commands
            for command_file in ms_dir.rglob("management/commands/*.py"):
                if command_file.name.startswith("_"): continue
                cmd_name = command_file.stem
                if cmd_name in COMMAND_EXCLUDE_LIST: continue
                sid = f"{ms_dir.name}-{cmd_name}"
                services[sid] = ServiceInfo(sid, cmd_name, ms_dir.name, str(ms_dir), ["manage.py", cmd_name], python_exe, port=None, project_type="mgmt")
        return services

# ----------------------------
# Venv manager
# ----------------------------
class VenvManager:
    def __init__(self, root: str):
        self.root = root
        self.venv_dir = os.path.join(root, '.venv_root')
    @property
    def python_executable(self) -> str:
        return os.path.join(self.venv_dir, 'Scripts', 'python.exe') if sys.platform == 'win32' else os.path.join(self.venv_dir, 'bin', 'python')
    def exists(self) -> bool:
        return os.path.exists(self.venv_dir) and os.path.exists(self.python_executable)
    def ensure(self):
        if not self.exists():
            logging.getLogger().action(f"Creating venv at {self.venv_dir}...")
            venv.create(self.venv_dir, with_pip=True)
    def install_requirements(self) -> bool:
        req_file = os.path.join(self.root, 'requirements.txt')
        if not os.path.exists(req_file):
            logging.getLogger().warning("No requirements.txt found.")
            return False
        cmd = [self.python_executable, '-m', 'pip', 'install', '-r', req_file]
        logging.getLogger().action(f"Running: {' '.join(cmd)}")
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in iter(proc.stdout.readline, ''): logging.getLogger().info(f"PIP: {line.strip()}")
        proc.wait()
        return proc.returncode == 0

# ----------------------------
# Service manager
# ----------------------------
class ServiceManager:
    def __init__(self):
        pass

    def _stream_output(self, process_obj: subprocess.Popen, log_queue: queue.Queue, display_name: str, logfile_path: Path):
        if not process_obj.stdout:
            return
        try:
            for line in iter(process_obj.stdout.readline, ''):
                if line is None: break
                try:
                    log_queue.put(line.rstrip())
                    with open(logfile_path, "a", encoding="utf-8", errors="replace") as lf:
                        lf.write(line)
                except Exception:
                    pass
        except Exception:
            pass
        process_obj.wait()
        log_queue.put(f"--- Process '{display_name}' exited with code {process_obj.returncode} ---")
        try:
            with open(logfile_path, "a", encoding="utf-8", errors="replace") as lf:
                lf.write(f"\n--- Process '{display_name}' exited with code {process_obj.returncode} ---\n")
        except Exception:
            pass

    def start(self, service: ServiceInfo) -> bool:
        if service.process and service.process.poll() is None:
            logging.getLogger().warning(f"Service '{service.unique_id}' already running.")
            return True

        service.status = 'starting'
        python_exe = service.python_exe or sys.executable
        args = [python_exe] + service.command
        logfile = LOG_DIR / f"{service.unique_id}.log"
        write_log_header_bytes(logfile, f"{service.unique_id} start")
        env = make_child_env(python_exe)
        logging.getLogger().action(f"Starting '{service.unique_id}': {' '.join(args)} (cwd={service.project_path})")
        try:
            creationflags = CREATE_NO_WINDOW if sys.platform == "win32" else 0
            p = subprocess.Popen(args, cwd=service.project_path, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, encoding='utf-8', errors='replace', bufsize=1, creationflags=creationflags)
        except Exception as e:
            logging.getLogger().error(f"Failed to spawn '{service.unique_id}': {e}")
            service.status = 'crashed'
            return False

        threading.Thread(target=self._stream_output, args=(p, service.log_queue, service.display_name, logfile), daemon=True).start()

        for attempt in range(1, MAX_RETRIES + 1):
            time.sleep(STARTUP_WAIT)
            if p.poll() is not None:
                logging.getLogger().error(f"Process '{service.unique_id}' exited early (rc={p.returncode}). See {logfile}")
                service.status = 'crashed'
                return False
            if service.port:
                if is_port_in_use(service.port):
                    service.process = p; service.pid = p.pid; service.status = 'running'
                    logging.getLogger().info(f"Service '{service.unique_id}' listening on port {service.port} (pid {p.pid})")
                    return True
                else:
                    logging.getLogger().warning(f"Service '{service.unique_id}' not yet listening (attempt {attempt}/{MAX_RETRIES})")
                    continue
            else:
                # no port expected (ms6 main or mgmt commands)
                service.process = p; service.pid = p.pid; service.status = 'running'
                logging.getLogger().info(f"Service '{service.unique_id}' started (pid {p.pid})")
                # if critical mgmt command, verify it opened expected ports
                if service.display_name in CRITICAL_MGMT_COMMANDS:
                    exp = CRITICAL_MGMT_COMMANDS[service.display_name].get("ports", [])
                    ok = any(is_port_in_use(pp) for pp in exp)
                    if not ok:
                        for _ in range(2):
                            time.sleep(STARTUP_WAIT)
                            if any(is_port_in_use(pp) for pp in exp):
                                ok = True; break
                    if not ok:
                        logging.getLogger().error(f"Critical mgmt '{service.unique_id}' did not open expected ports.")
                        try:
                            p.kill()
                        except Exception:
                            pass
                        service.status = 'crashed'
                        return False
                return True

        logging.getLogger().error(f"Service '{service.unique_id}' failed to become healthy after {MAX_RETRIES} attempts")
        try:
            p.kill()
        except Exception:
            pass
        service.status = 'crashed'
        return False

    def stop(self, service: ServiceInfo):
        p = service.process
        if not p or p.poll() is not None:
            service.status = 'stopped'
            return
        logging.getLogger().action(f"Stopping '{service.unique_id}' (pid={service.pid})")
        try:
            p.terminate()
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            logging.getLogger().warning(f"'{service.unique_id}' unresponsive; killing.")
            try:
                p.kill()
            except Exception:
                pass
        service.process = None
        service.pid = None
        service.status = 'stopped'

    def restart(self, service: ServiceInfo):
        self.stop(service)
        time.sleep(0.5)
        self.start(service)

# ----------------------------
# Resource monitor (robust)
# ----------------------------
class ResourceMonitor:
    def snapshot(self, service: ServiceInfo):
        if not service.pid or service.status != 'running':
            return {}
        try:
            proc = psutil.Process(service.pid)
            with proc.oneshot():
                # cross-platform: use proc.connections
                conns = proc.connections(kind='inet')
                ports = [str(c.laddr.port) for c in conns if c.status == psutil.CONN_LISTEN and getattr(c, 'laddr', None)]
                return {
                    'pid': service.pid,
                    'cpu': proc.cpu_percent(interval=None),
                    'mem_rss': proc.memory_info().rss,
                    'mem_percent': proc.memory_percent(),
                    'threads': proc.num_threads(),
                    'ports': ports,
                }
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logging.getLogger().warning(f"ResourceMonitor: process {service.pid} not accessible: {e}")
            service.status = 'crashed'
            service.pid = None
            service.process = None
            return {}
        except AttributeError as e:
            logging.getLogger().warning(f"ResourceMonitor: AttributeError for pid {service.pid}: {e}. Falling back to global net_connections.")
            try:
                ports = []
                for conn in psutil.net_connections(kind='inet'):
                    try:
                        if conn.pid == service.pid and conn.status == psutil.CONN_LISTEN and conn.laddr:
                            ports.append(str(conn.laddr.port))
                    except Exception:
                        pass
                proc = psutil.Process(service.pid)
                return {
                    'pid': service.pid,
                    'cpu': proc.cpu_percent(interval=None),
                    'mem_rss': proc.memory_info().rss,
                    'mem_percent': proc.memory_percent(),
                    'threads': proc.num_threads(),
                    'ports': ports,
                }
            except Exception as e2:
                logging.getLogger().error(f"ResourceMonitor fallback failed for pid {service.pid}: {e2}")
                service.status = 'crashed'
                service.pid = None
                service.process = None
                return {}
        except Exception as e:
            logging.getLogger().error(f"ResourceMonitor general error for pid {service.pid}: {e}")
            service.status = 'crashed'
            service.pid = None
            service.process = None
            return {}

# ----------------------------
# Sound manager (disabled by default)
# ----------------------------
class SoundManager:
    def __init__(self, root_path: str):
        self._disabled = os.environ.get("ENABLE_SOUNDS", "0") != "1"
        self._multimedia_available = True
        try:
            from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
            self._QMediaPlayer = QMediaPlayer
            self._QAudioOutput = QAudioOutput
        except Exception:
            self._multimedia_available = False
            logging.getLogger().warning("PySide6 multimedia not available; sound disabled.")
            self._QMediaPlayer = None
            self._QAudioOutput = None

        self.good_player = None
        self.bad_player = None
        self.stopping_player = None

        if not self._disabled and self._multimedia_available:
            self.good_player = self._setup_player("good sound.mp3", root_path)
            self.bad_player = self._setup_player("bad sound.mp3", root_path)
            self.stopping_player = self._setup_player("stopping sound .mp3", root_path)
        else:
            logging.getLogger().info(f"SoundManager: sounds {'disabled' if self._disabled else 'unavailable'}.")

    def _setup_player(self, filename: str, root_path: str):
        path = os.path.join(root_path, filename)
        if not self._multimedia_available or self._disabled:
            return None
        if not os.path.exists(path):
            logging.getLogger().warning(f"Sound file '{filename}' not found at {path}. Sound will be skipped.")
            return None
        try:
            player = self._QMediaPlayer()
            audio_output = self._QAudioOutput()
            player.setAudioOutput(audio_output)
            player.setSource(QUrl.fromLocalFile(path))
            player._audio_output_device = audio_output
            return player
        except Exception as e:
            logging.getLogger().warning(f"Failed to setup audio player for '{filename}': {e}")
            return None

    def play_good(self):
        if self.good_player:
            try: self.good_player.play()
            except Exception as e: logging.getLogger().warning(f"play_good failed: {e}")

    def play_stopping(self):
        if self.stopping_player:
            try: self.stopping_player.play()
            except Exception as e: logging.getLogger().warning(f"play_stopping failed: {e}")

    def _start_loop(self, player):
        if not player: return
        try:
            try:
                player.setLoops(player.Loops.Infinite)
            except Exception:
                try:
                    from PySide6.QtMultimedia import QMediaPlayer as _QMP
                    player.setLoops(_QMP.Loops.Infinite)
                except Exception:
                    pass
            if player.playbackState() != player.PlaybackState.PlayingState:
                player.play()
        except Exception as e:
            logging.getLogger().warning(f"_start_loop failed: {e}")

    def _stop_loop(self, player):
        if not player: return
        try:
            if player.playbackState() == player.PlaybackState.PlayingState:
                player.stop()
                try:
                    player.setLoops(player.Loops.Once)
                except Exception:
                    pass
        except Exception as e:
            logging.getLogger().warning(f"_stop_loop failed: {e}")

    def start_bad_loop(self): self._start_loop(self.bad_player)
    def stop_bad_loop(self): self._stop_loop(self.bad_player)
    def start_stopping_loop(self): self._start_loop(self.stopping_player)
    def stop_stopping_loop(self): self._stop_loop(self.stopping_player)

# ----------------------------
# Main GUI Window
# ----------------------------
class MainWindow(QWidget):
    def __init__(self, root: str):
        super().__init__()
        self.root = root
        self.vmgr = VenvManager(root)
        self.svc_mgr = ServiceManager()
        self.services = ProjectScanner(root).scan()
        self.monitor = ResourceMonitor()
        self.sound_manager = SoundManager(root)
        self.crashed_services_triggering_sound: Set[str] = set()
        self.service_terminals: Dict[str, QTextEdit] = {}
        self.setWindowTitle('Django Multi-Project Orchestrator')
        self.resize(1400, 900)

        self._setup_ui()
        self._populate_trees()
        self._start_timers()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(); layout.addWidget(self.tabs)

        # Controls tab
        ctrl = QWidget(); self.tabs.addTab(ctrl, '🚀 Controls & Main Log')
        layout_ctrl = QVBoxLayout(ctrl)
        top = QHBoxLayout(); layout_ctrl.addLayout(top)
        self.venv_label = QLabel(f'Venv: {self.vmgr.venv_dir}'); top.addWidget(self.venv_label)
        btn_ensure = QPushButton('Setup Environment & Install Dependencies'); btn_ensure.clicked.connect(self._ensure_venv)
        top.addWidget(btn_ensure)
        self.services_tree = QTreeWidget(); self.services_tree.setHeaderLabels(['Service', 'Status', 'Controls'])
        self.services_tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.services_tree.setColumnWidth(2, 240)
        layout_ctrl.addWidget(self.services_tree, stretch=1)

        bottom = QHBoxLayout(); layout_ctrl.addLayout(bottom)
        self.btn_start_all = QPushButton('▶️ Start'); self.btn_start_all.clicked.connect(lambda: threading.Thread(target=self._start_all_worker, daemon=True).start())
        self.btn_stop_all = QPushButton('⏹️ Stop'); self.btn_stop_all.clicked.connect(lambda: threading.Thread(target=self._stop_all_worker, daemon=True).start())
        self.btn_restart_all = QPushButton('🔄 Restart'); self.btn_restart_all.clicked.connect(lambda: threading.Thread(target=self._restart_all_worker, daemon=True).start())
        bottom.addWidget(self.btn_start_all); bottom.addWidget(self.btn_stop_all); bottom.addWidget(self.btn_restart_all)
        bottom.addStretch()
        btn_kill = QPushButton('🔪 Force Clean Ports'); btn_kill.clicked.connect(lambda: threading.Thread(target=self._force_kill_ports_worker, daemon=True).start())
        bottom.addWidget(btn_kill)
        bottom.addWidget(QLabel("<b>Docker:</b>"))
        btn_up = QPushButton('🐳 Up'); btn_up.clicked.connect(lambda: threading.Thread(target=self._docker_worker, args=(['up','-d'], False), daemon=True).start())
        btn_down = QPushButton('🔻 Down'); btn_down.clicked.connect(lambda: threading.Thread(target=self._docker_worker, args=(['down'], True), daemon=True).start())
        bottom.addWidget(btn_up); bottom.addWidget(btn_down)

        self.root_terminal = QTextEdit(); self.root_terminal.setReadOnly(True); self.root_terminal.setFont(QFont("Consolas", 10))
        layout_ctrl.addWidget(self.root_terminal, stretch=1)

        # Logs tab
        logs_tab = QWidget(); self.tabs.addTab(logs_tab, '📜 Service Logs')
        layout_logs = QHBoxLayout(logs_tab)
        self.service_log_tree = QTreeWidget(); self.service_log_tree.setHeaderHidden(True); self.service_log_tree.setMaximumWidth(250)
        self.service_log_tree.currentItemChanged.connect(self._on_log_service_selected)
        layout_logs.addWidget(self.service_log_tree)
        self.terminal_stack = QStackedWidget(); layout_logs.addWidget(self.terminal_stack, stretch=1)

        # Monitor tab
        mon_tab = QWidget(); self.tabs.addTab(mon_tab, '📊 Resource Monitor')
        layout_mon = QVBoxLayout(mon_tab)
        self.monitor_table = QTreeWidget(); self.monitor_table.setHeaderLabels(['Svc','PID','CPU%','Mem(MB)','Mem%','Threads','Ports'])
        layout_mon.addWidget(self.monitor_table)

    def _populate_trees(self):
        projects = {}; projects_logs = {}
        sorted_services = sorted(self.services.values(), key=lambda s: natural_sort_key(s.unique_id))
        for svc in sorted_services:
            if svc.project_name not in projects:
                projects[svc.project_name] = QTreeWidgetItem(self.services_tree, [svc.project_name])
                projects[svc.project_name].setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
            parent = projects[svc.project_name]
            child = QTreeWidgetItem(None, [f"  └─ {svc.display_name}", svc.status])
            parent.addChild(child)
            svc.tree_item = child

            btns = QWidget(); btn_layout = QHBoxLayout(btns); btn_layout.setContentsMargins(0,0,0,0)
            for action, icon in [('start','▶️'), ('stop','⏹️'), ('restart','🔄')]:
                btn = QPushButton(icon)
                cb = functools.partial(self._control_service_threadsafe, svc, action, btn)
                btn.clicked.connect(cb)
                svc.control_buttons[action] = btn; btn_layout.addWidget(btn)
            self.services_tree.setItemWidget(child, 2, btns)

            if svc.project_name not in projects_logs:
                projects_logs[svc.project_name] = QTreeWidgetItem(self.service_log_tree, [svc.project_name])
                projects_logs[svc.project_name].setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
            parent_log = projects_logs[svc.project_name]
            child_log = QTreeWidgetItem(None, [svc.display_name])
            child_log.setData(0, Qt.ItemDataRole.UserRole, svc.unique_id)
            parent_log.addChild(child_log)

            term = QTextEdit(); term.setReadOnly(True); term.setFont(QFont("Consolas", 10))
            self.service_terminals[svc.unique_id] = term; self.terminal_stack.addWidget(term)
        self.services_tree.expandAll(); self.service_log_tree.expandAll()

    def _start_timers(self):
        self.log_timer = QTimer(self); self.log_timer.timeout.connect(self._drain_logs); self.log_timer.start(150)
        self.monitor_timer = QTimer(self); self.monitor_timer.timeout.connect(self._update_monitor); self.monitor_timer.start(1500)
        self.status_timer = QTimer(self); self.status_timer.timeout.connect(self._update_statuses); self.status_timer.start(1000)

    # Venv
    def _ensure_venv(self):
        threading.Thread(target=self._ensure_venv_worker, daemon=True).start()
    def _ensure_venv_worker(self):
        try:
            self.vmgr.ensure()
            logging.getLogger().info("Venv ready")
            if self.vmgr.exists():
                # set svc manager venv Python if required (it uses service.python_exe already)
                self.venv_label.setText(f'Venv: {self.vmgr.venv_dir} [OK]')
            if self.vmgr.install_requirements():
                self.sound_manager.play_good()
        except Exception as e:
            logging.getLogger().critical(f"Venv setup failed: {e}")

    # Buttons for individual service control (thread-safe)
    def _control_service_threadsafe(self, service: ServiceInfo, action: str, btn: QPushButton):
        # disable all control buttons for this service while action runs
        for b in service.control_buttons.values():
            b.setEnabled(False)
        def worker():
            try:
                if action == 'start':
                    ok = self.svc_mgr.start(service)
                    if ok: self.sound_manager.play_good()
                elif action == 'stop':
                    self.svc_mgr.stop(service)
                    self.sound_manager.play_stopping()
                elif action == 'restart':
                    self.svc_mgr.restart(service)
                    self.sound_manager.play_good()
            except Exception as e:
                logging.getLogger().error(f"Control {action} failed for {service.unique_id}: {e}")
            finally:
                # update button states based on resulting service.status
                is_running = service.status == 'running'
                for a, b in service.control_buttons.items():
                    if a == 'start':
                        b.setEnabled(not is_running)
                    else:
                        b.setEnabled(is_running)
        threading.Thread(target=worker, daemon=True).start()

    # Start/stop/restart all
    def _start_all_worker(self):
        if not force_kill_ports(ALL_PORTS_TO_CLEAR):
            logging.getLogger().error("Could not clear ports; aborting start-all.")
            return
        services_by_project = {}
        for svc in self.services.values():
            services_by_project.setdefault(svc.project_name, []).append(svc)
        for proj in sorted(services_by_project.keys(), key=natural_sort_key):
            for svc in sorted(services_by_project[proj], key=lambda s: natural_sort_key(s.unique_id)):
                ok = self.svc_mgr.start(svc)
                if not ok:
                    logging.getLogger().critical(f"Failed to start critical service {svc.unique_id}. Aborting remaining starts.")
                    return
        logging.getLogger().info("Start all completed.")

    def _stop_all_worker(self):
        self.sound_manager.start_stopping_loop()
        try:
            for svc in list(self.services.values()):
                self.svc_mgr.stop(svc)
            self.sound_manager.play_good()
        finally:
            self.sound_manager.stop_stopping_loop()

    def _restart_all_worker(self):
        self._stop_all_worker()
        time.sleep(0.5)
        self._start_all_worker()

    def _force_kill_ports_worker(self):
        self.sound_manager.start_stopping_loop()
        try:
            ok = force_kill_ports(ALL_PORTS_TO_CLEAR)
            logging.getLogger().info(f"force_kill_ports result: {ok}")
        finally:
            self.sound_manager.stop_stopping_loop()

    # Docker worker with conflict detection + one retry
    def _docker_worker(self, command: List[str], is_bad: bool):
        if is_bad:
            self.sound_manager.start_stopping_loop()
        try:
            compose_path = _find_compose_file(self.root)
            if not compose_path:
                tried = ["docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"]
                logging.getLogger().error(f"Docker failed: no compose file found. Tried: {tried}")
                return
            base_cmd = _get_docker_cmd()
            full_cmd = base_cmd + command
            cmd_display = " ".join(shlex_quote(x) for x in full_cmd)
            logging.getLogger().action(f"Running: {cmd_display} (compose file: {compose_path})")

            def run_and_capture(cmd_list):
                proc = subprocess.Popen(cmd_list, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True, bufsize=1, creationflags=CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
                                        env=os.environ.copy())
                out_lines = []
                for line in iter(proc.stdout.readline, ''):
                    if not line:
                        break
                    msg = line.rstrip()
                    out_lines.append(msg)
                    logging.getLogger().info(f"DOCKER: {msg}")
                proc.wait()
                return proc.returncode, "\n".join(out_lines)

            rc, out = run_and_capture(full_cmd)
            if rc == 0:
                logging.getLogger().info("SUCCESS: Docker command finished.")
                if not is_bad:
                    self.sound_manager.play_good()
                return

            logging.getLogger().error(f"Docker command failed with returncode {rc}")

            # Detect container name conflict
            m = re.search(r'container name "(/?[^"]+)" is already in use by container "([0-9a-f]+)"', out, re.IGNORECASE)
            if m:
                conflict_name = m.group(1); conflict_id = m.group(2)
                logging.getLogger().warning(f"Detected container-name conflict: {conflict_name} (id {conflict_id}). Attempting docker rm -f {conflict_id} and retry.")
                try:
                    subprocess.run(["docker", "rm", "-f", conflict_id], cwd=self.root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    logging.getLogger().info(f"Removed conflicting container {conflict_id}. Retrying docker up once.")
                except Exception as e:
                    logging.getLogger().error(f"Failed to remove conflicting container {conflict_id}: {e}")
                    return
                rc2, out2 = run_and_capture(full_cmd)
                if rc2 == 0:
                    logging.getLogger().info("SUCCESS (after removing conflict): Docker command finished.")
                    if not is_bad:
                        self.sound_manager.play_good()
                    return
                else:
                    logging.getLogger().error(f"Retry also failed (returncode {rc2}). Output:\n{out2}")
                    return

            logging.getLogger().error("Docker failure output (no conflict detected):\n" + out)
        except FileNotFoundError as fnf:
            logging.getLogger().error(f"Docker binary not found: {fnf}")
        except Exception as e:
            logging.getLogger().error(f"Docker failed: {e}")
        finally:
            if is_bad:
                self.sound_manager.stop_stopping_loop()

    # Log draining and UI updates
    def _drain_logs(self):
        for uid, term in self.service_terminals.items():
            svc = self.services.get(uid)
            if not svc: continue
            appended = False
            while not svc.log_queue.empty():
                try:
                    line = svc.log_queue.get_nowait()
                    term.append(line)
                    appended = True
                except queue.Empty:
                    break
            if appended and term is self.terminal_stack.currentWidget():
                term.verticalScrollBar().setValue(term.verticalScrollBar().maximum())

    def _update_monitor(self):
        self.monitor_table.clear()
        projects = {}
        for svc in sorted(self.services.values(), key=lambda s: natural_sort_key(s.unique_id)):
            if svc.project_name not in projects:
                projects[svc.project_name] = QTreeWidgetItem(self.monitor_table, [svc.project_name])
                projects[svc.project_name].setFont(0, QFont("Segoe UI", 10, QFont.Weight.Bold))
            parent = projects[svc.project_name]
            try:
                snap = self.monitor.snapshot(svc)
            except Exception as e:
                logging.getLogger().error(f"_update_monitor: snapshot failed for {svc.unique_id}: {e}")
                snap = {}
            data = [f"  └─ {svc.display_name}", str(snap.get('pid','-')), f"{snap.get('cpu',0):.1f}", f"{snap.get('mem_rss',0)/(1024*1024):.2f}", f"{snap.get('mem_percent',0):.2f}", str(snap.get('threads','-')), ','.join(snap.get('ports',[])) or '-']
            child = QTreeWidgetItem(parent, data)
            if svc.status == 'crashed': child.setForeground(0, QColor('red'))
            elif svc.status != 'running': child.setForeground(0, QColor('gray'))
        self.monitor_table.expandAll()

    def _update_statuses(self):
        colors = {'running': '#aaffaa', 'stopped': '#ffaaaa', 'starting': '#ffffaa', 'stopping': '#ffccaa', 'crashed': '#ff88ff'}
        for svc in self.services.values():
            if svc.process and svc.process.poll() is not None:
                svc.status = 'crashed' if svc.process.returncode != 0 else 'stopped'
                svc.pid = None; svc.process = None
            if svc.status == 'crashed':
                self.crashed_services_triggering_sound.add(svc.unique_id)
            else:
                self.crashed_services_triggering_sound.discard(svc.unique_id)
            is_running = svc.status == 'running'
            if svc.tree_item:
                svc.tree_item.setText(1, svc.status)
                svc.tree_item.setBackground(1, QColor(colors.get(svc.status, '#ffffff')))
            for a, b in svc.control_buttons.items():
                if a == 'start':
                    b.setEnabled(not is_running)
                else:
                    b.setEnabled(is_running)
        if self.crashed_services_triggering_sound:
            self.sound_manager.start_bad_loop()
        else:
            self.sound_manager.stop_bad_loop()

    def _on_log_service_selected(self, current, _):
        if not current:
            return
        uid = current.data(0, Qt.ItemDataRole.UserRole)
        if uid and uid in self.service_terminals:
            self.terminal_stack.setCurrentWidget(self.service_terminals[uid])

    def closeEvent(self, event: QCloseEvent):
        logging.getLogger().action("Close event: stopping all running services...")
        self.sound_manager.start_stopping_loop()
        for svc in list(self.services.values()):
            self.svc_mgr.stop(svc)
        self.sound_manager.stop_stopping_loop()
        event.accept()

# ----------------------------
# Small helpers
# ----------------------------
def shlex_quote(s: str) -> str:
    # simple quoting for display
    return '"' + s.replace('"', '\\"') + '"' if ' ' in s or '"' in s else s

# ----------------------------
# Entrypoint
# ----------------------------
def main():
    # logging setup
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)-8s - %(message)s', datefmt='%H:%M:%S')
    logging.addLevelName(logging.INFO + 1, 'ACTION')
    def action(self, message, *args, **kws): self._log(logging.INFO + 1, message, args, **kws)
    logging.Logger.action = action

    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))

    win = MainWindow(os.getcwd())

    # Wire logging -> GUI via signal handler (thread-safe)
    log_emitter = LogEmitter()
    log_emitter.append_html.connect(win.root_terminal.append)
    handler = QtLogHandler(log_emitter)
    formatter = ColoredFormatter('%(asctime)s - %(levelname)-8s - %(message)s', datefmt='%H:%M:%S')
    handler.setFormatter(formatter)
    logger = logging.getLogger()
    logger.addHandler(handler)

    # route stdout/stderr to logging
    sys.stdout = StreamToLogger(logger, logging.INFO)
    sys.stderr = StreamToLogger(logger, logging.ERROR)

    win.show()
    logging.getLogger().info(f"Orchestrator started. Found {len(win.services)} runnable services.")
    if shutil.which("docker"):
        try:
            out = subprocess.run(['docker','--version'], capture_output=True, text=True, check=False)
            logging.getLogger().info(f"Docker found: {out.stdout.strip()}")
        except Exception:
            pass
    if shutil.which("docker-compose"):
        try:
            out = subprocess.run(['docker-compose','--version'], capture_output=True, text=True, check=False)
            logging.getLogger().info(f"Docker-compose found: {out.stdout.strip()}")
        except Exception:
            pass

    sys.exit(app.exec())

if __name__ == '__main__':
    main()
