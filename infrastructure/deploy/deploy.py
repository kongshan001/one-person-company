#!/usr/bin/env python3
"""
一键部署脚本 - 将所有产品部署为后台服务

用法:
  python deploy.py          # 启动所有服务
  python deploy.py --stop   # 停止所有服务
  python deploy.py --status # 查看服务状态
"""

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

# 项目根目录
ROOT_DIR = Path(__file__).parent.parent

SERVICES = {
    "icon-forge": {
        "script": str(ROOT_DIR / "products" / "icon-forge" / "generate.py"),
        "type": "cli",  # 按需运行, 不是常驻服务
    },
    "paste-hut": {
        "script": str(ROOT_DIR / "products" / "paste-hut" / "server.py"),
        "port": 9292,
        "type": "http",
    },
    "ping-bot": {
        "script": str(ROOT_DIR / "products" / "ping-bot" / "monitor.py"),
        "port": 8081,
        "type": "http",
    },
}

PID_DIR = Path("/tmp/onepersonco-pids")


def get_pid(service_name: str) -> int:
    """获取服务的PID"""
    pid_file = PID_DIR / f"{service_name}.pid"
    if pid_file.exists():
        try:
            return int(pid_file.read_text().strip())
        except ValueError:
            return None
    return None


def is_running(pid: int) -> bool:
    """检查进程是否在运行"""
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def start_service(name: str, config: dict):
    """启动单个服务"""
    pid = get_pid(name)
    if pid and is_running(pid):
        print(f"  ✅ {name} already running (PID {pid})")
        return
    
    PID_DIR.mkdir(parents=True, exist_ok=True)
    
    if config["type"] == "http":
        cmd = [sys.executable, config["script"], "--port", str(config["port"])]
        process = subprocess.Popen(
            cmd,
            stdout=open(f"/tmp/{name}.log", "w"),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        pid_file = PID_DIR / f"{name}.pid"
        pid_file.write_text(str(process.pid))
        print(f"  🚀 {name} started (PID {process.pid}, port {config['port']})")
    else:
        print(f"  ℹ️ {name} is a CLI tool, use directly: python {config['script']}")


def stop_service(name: str):
    """停止单个服务"""
    pid = get_pid(name)
    if not pid:
        print(f"  ⏹️ {name} not running")
        return
    
    if is_running(pid):
        os.kill(pid, signal.SIGTERM)
        print(f"  🛑 {name} stopped (PID {pid})")
    else:
        print(f"  ⏹️ {name} not running (stale PID)")
    
    pid_file = PID_DIR / f"{name}.pid"
    if pid_file.exists():
        pid_file.unlink()


def show_status():
    """显示所有服务状态"""
    print("\n📊 OnePersonCo Service Status\n")
    for name, config in SERVICES.items():
        pid = get_pid(name)
        running = is_running(pid) if pid else False
        
        if config["type"] == "http":
            status = f"🟢 Running (PID {pid})" if running else "🔴 Stopped"
            port_info = f" → http://localhost:{config['port']}"
        else:
            status = "📋 CLI Tool"
            port_info = ""
        
        print(f"  {name:15} {status}{port_info}")
    print()


def main():
    parser = argparse.ArgumentParser(description="OnePersonCo Deploy")
    parser.add_argument("--stop", action="store_true", help="Stop all services")
    parser.add_argument("--status", action="store_true", help="Show status")
    parser.add_argument("--service", help="Start/stop specific service")
    args = parser.parse_args()
    
    if args.status:
        show_status()
        return
    
    targets = {args.service: SERVICES[args.service]} if args.service else SERVICES
    
    if args.stop:
        print("🛑 Stopping services...")
        for name, config in targets.items():
            stop_service(name)
    else:
        print("🚀 Starting services...")
        for name, config in targets.items():
            start_service(name, config)
    
    show_status()


if __name__ == "__main__":
    main()
