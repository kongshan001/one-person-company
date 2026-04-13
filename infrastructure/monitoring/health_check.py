#!/usr/bin/env python3
"""
健康检查脚本 - 监控所有服务的运行状态
可独立运行，也可由 cron 定期调用

用法:
  python health_check.py           # 检查并打印
  python health_check.py --json    # JSON 输出
  python health_check.py --alert   # 失败时发送告警 (需要配置)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

# 引入共享工具
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from utils import send_json as _send_json_util, send_html as _send_html_util, send_cors_headers as _send_cors


# ============ 检查项 ============

def check_http(url: str, timeout: int = 5) -> dict:
    """检查 HTTP 服务"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "PingBot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {
                "status": "up",
                "code": resp.status,
                "url": url,
            }
    except Exception as e:
        return {
            "status": "down",
            "error": str(e),
            "url": url,
        }


def check_disk(path: str = "/", threshold_gb: float = 1.0) -> dict:
    """检查磁盘空间"""
    try:
        usage = shutil.disk_usage(path)
        free_gb = usage.free / (1024 ** 3)
        return {
            "status": "ok" if free_gb > threshold_gb else "warning",
            "free_gb": round(free_gb, 2),
            "total_gb": round(usage.total / (1024 ** 3), 2),
            "used_pct": round(usage.used / usage.total * 100, 1),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_memory() -> dict:
    """检查内存使用 (Linux only)"""
    try:
        with open("/proc/meminfo") as f:
            lines = f.readlines()
        info = {}
        for line in lines:
            parts = line.split()
            key = parts[0].rstrip(":")
            value = int(parts[1])  # KB
            info[key] = value
        
        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", 0)
        used_pct = round((total - available) / total * 100, 1) if total else 0
        
        return {
            "status": "ok" if used_pct < 90 else "warning",
            "total_mb": round(total / 1024),
            "available_mb": round(available / 1024),
            "used_pct": used_pct,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_load() -> dict:
    """检查系统负载"""
    try:
        load1, load5, load15 = os.getloadavg()
        cpu_count = os.cpu_count() or 1
        return {
            "status": "ok" if load1 < cpu_count * 2 else "warning",
            "load_1m": round(load1, 2),
            "load_5m": round(load5, 2),
            "load_15m": round(load15, 2),
            "cpu_count": cpu_count,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def check_process(port: int) -> dict:
    """检查监听端口的进程"""
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-t"],
            capture_output=True, text=True, timeout=5
        )
        pids = result.stdout.strip().split("\n") if result.stdout.strip() else []
        return {
            "status": "up" if pids else "down",
            "port": port,
            "pids": pids,
        }
    except Exception as e:
        return {"status": "unknown", "port": port, "error": str(e)}


# ============ 主流程 ============

def run_checks() -> dict:
    """运行所有检查"""
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "hostname": os.uname().nodename,
        "services": {},
        "system": {},
    }
    
    # 服务检查
    services = [
        ("PasteHut", "http://localhost:9292/health"),
        ("PingBot", "http://localhost:8081/health"),
    ]
    for name, url in services:
        results["services"][name] = check_http(url)
    
    # 系统检查
    results["system"]["disk"] = check_disk()
    results["system"]["memory"] = check_memory()
    results["system"]["load"] = check_load()
    
    # 汇总
    all_up = all(
        s["status"] in ("up", "ok")
        for s in results["services"].values()
    )
    sys_ok = all(
        s["status"] in ("ok", "up")
        for s in results["system"].values()
    )
    results["overall"] = "healthy" if (all_up and sys_ok) else "degraded"
    
    return results


def print_report(results: dict):
    """打印报告"""
    status_emoji = {"healthy": "✅", "degraded": "⚠️", "down": "❌", "ok": "✅", "warning": "⚠️", "up": "🟢", "error": "🔴"}
    
    emoji = status_emoji.get(results["overall"], "❓")
    print(f"\n{emoji} System Status: {results['overall'].upper()}")
    print(f"   Host: {results['hostname']}")
    print(f"   Time: {results['timestamp']}\n")
    
    print("📡 Services:")
    for name, info in results["services"].items():
        s = status_emoji.get(info["status"], "❓")
        detail = f" (HTTP {info.get('code', '?')})" if "code" in info else f" ({info.get('error', 'unknown')})"
        print(f"   {s} {name}: {info['status']}{detail}")
    
    print("\n💻 System:")
    for name, info in results["system"].items():
        s = status_emoji.get(info["status"], "❓")
        if name == "disk":
            print(f"   {s} Disk: {info['free_gb']}GB free / {info['total_gb']}GB ({info['used_pct']}% used)")
        elif name == "memory":
            print(f"   {s} Memory: {info['available_mb']}MB free / {info['total_mb']}MB ({info['used_pct']}% used)")
        elif name == "load":
            print(f"   {s} Load: {info['load_1m']} / {info['load_5m']} / {info['load_15m']} ({info['cpu_count']} CPUs)")
    
    print()


def format_prometheus(results: dict) -> str:
    """将检查结果格式化为 Prometheus 兼容的 metrics 文本格式

    输出示例::

        # HELP opc_system_up System overall status (1=healthy, 0=degraded)
        # TYPE opc_system_up gauge
        opc_system_up 1
        # HELP opc_service_up Service status (1=up, 0=down)
        # TYPE opc_service_up gauge
        opc_service_up{service="PasteHut"} 1
        opc_service_up{service="PingBot"} 1
        # HELP opc_disk_free_bytes Free disk space in bytes
        # TYPE opc_disk_free_bytes gauge
        opc_disk_free_bytes 1.073741824e+10
        # HELP opc_disk_used_pct Disk usage percentage
        # TYPE opc_disk_used_pct gauge
        opc_disk_used_pct 45.2
        # HELP opc_memory_available_bytes Available memory in bytes
        # TYPE opc_memory_available_bytes gauge
        opc_memory_available_bytes 2.147483648e+09
        # HELP opc_memory_used_pct Memory usage percentage
        # TYPE opc_memory_used_pct gauge
        opc_memory_used_pct 62.3
        # HELP opc_load_1m System load average (1 min)
        # TYPE opc_load_1m gauge
        opc_load_1m 0.52

    Args:
        results: run_checks() 返回的结果字典

    Returns:
        Prometheus exposition format 文本
    """
    lines = []
    status_val = 1 if results.get("overall") == "healthy" else 0

    lines.append("# HELP opc_system_up System overall status (1=healthy, 0=degraded)")
    lines.append("# TYPE opc_system_up gauge")
    lines.append(f"opc_system_up {status_val}")

    # Service status
    lines.append("# HELP opc_service_up Service status (1=up, 0=down)")
    lines.append("# TYPE opc_service_up gauge")
    for name, info in results.get("services", {}).items():
        val = 1 if info.get("status") in ("up", "ok") else 0
        lines.append(f'opc_service_up{{service="{name}"}} {val}')

    # Disk
    disk = results.get("system", {}).get("disk", {})
    if "free_gb" in disk:
        free_bytes = disk["free_gb"] * (1024 ** 3)
        lines.append("# HELP opc_disk_free_bytes Free disk space in bytes")
        lines.append("# TYPE opc_disk_free_bytes gauge")
        lines.append(f"opc_disk_free_bytes {free_bytes:.0f}")
    if "used_pct" in disk:
        lines.append("# HELP opc_disk_used_pct Disk usage percentage")
        lines.append("# TYPE opc_disk_used_pct gauge")
        lines.append(f"opc_disk_used_pct {disk['used_pct']}")

    # Memory
    mem = results.get("system", {}).get("memory", {})
    if "available_mb" in mem:
        avail_bytes = mem["available_mb"] * (1024 ** 2)
        lines.append("# HELP opc_memory_available_bytes Available memory in bytes")
        lines.append("# TYPE opc_memory_available_bytes gauge")
        lines.append(f"opc_memory_available_bytes {avail_bytes:.0f}")
    if "used_pct" in mem:
        lines.append("# HELP opc_memory_used_pct Memory usage percentage")
        lines.append("# TYPE opc_memory_used_pct gauge")
        lines.append(f"opc_memory_used_pct {mem['used_pct']}")

    # Load
    load = results.get("system", {}).get("load", {})
    if "load_1m" in load:
        lines.append("# HELP opc_load_1m System load average (1 min)")
        lines.append("# TYPE opc_load_1m gauge")
        lines.append(f"opc_load_1m {load['load_1m']}")

    return "\n".join(lines) + "\n"


def serve_http(port: int = 9100, host: str = "0.0.0.0"):
    """以 HTTP 服务模式运行，暴露 JSON 和 Prometheus 指标端点

    端点:
      GET /health         - JSON 格式健康状态
      GET /metrics        - Prometheus exposition format
      GET /               - 人类可读仪表盘

    Args:
        port: 监听端口，默认 9100（Prometheus node_exporter 兼容）
        host: 监听地址，默认 0.0.0.0
    """
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse

    class HealthHandler(BaseHTTPRequestHandler):
        """健康检查 HTTP Handler"""

        def do_GET(self):
            path = urllib.parse.urlparse(self.path).path
            results = run_checks()

            if path == "/health":
                self._send_json_resp(results)
            elif path == "/metrics":
                prom_text = format_prometheus(results)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                self.end_headers()
                self.wfile.write(prom_text.encode())
            elif path == "/":
                self._send_dashboard(results)
            else:
                self._send_json_resp({"error": "Not found"}, 404)

        def _send_json_resp(self, data: dict, status: int = 200):
            """发送 JSON 响应（使用 utils.send_json）"""
            _send_json_util(self, data, status=status)

        def _send_dashboard(self, results: dict):
            status_emoji = {"healthy": "✅", "degraded": "⚠️", "down": "❌", "ok": "✅", "warning": "⚠️", "up": "🟢", "error": "🔴"}
            emoji = status_emoji.get(results["overall"], "❓")
            html_parts = [
                "<!DOCTYPE html><html><head><meta charset='utf-8'>",
                "<title>OnePersonCo Health</title>",
                "<style>",
                "body{font-family:system-ui;background:#1a1a2e;color:#eee;max-width:900px;margin:40px auto;padding:20px}",
                "h1{color:#e94560}table{width:100%;border-collapse:collapse;margin:16px 0}",
                "th,td{padding:10px 14px;text-align:left;border-bottom:1px solid #333}",
                "th{background:#0f3460;color:#eee}.up{color:#2ecc71}.down{color:#e74c3c}",
                ".card{background:#16213e;padding:20px;border-radius:8px;margin:12px 0}",
                "a{color:#e94560}footer{color:#888;margin-top:32px;text-align:center}",
                "</style></head><body>",
                f"<h1>{emoji} OnePersonCo Health Dashboard</h1>",
                f"<p>Status: <strong>{results['overall'].upper()}</strong> | Host: {results['hostname']} | Time: {results['timestamp']}</p>",
            ]
            # Services table
            if results.get("services"):
                html_parts.append("<div class='card'><h2>📡 Services</h2><table><tr><th>Service</th><th>Status</th><th>Detail</th></tr>")
                for name, info in results["services"].items():
                    s = status_emoji.get(info["status"], "❓")
                    detail = f"HTTP {info.get('code', '?')}" if "code" in info else info.get("error", "unknown")
                    cls = "up" if info["status"] in ("up", "ok") else "down"
                    html_parts.append(f"<tr><td>{name}</td><td class='{cls}'>{s} {info['status']}</td><td>{detail}</td></tr>")
                html_parts.append("</table></div>")
            # System table
            if results.get("system"):
                html_parts.append("<div class='card'><h2>💻 System</h2><table><tr><th>Metric</th><th>Value</th></tr>")
                for name, info in results["system"].items():
                    s = status_emoji.get(info.get("status", "ok"), "❓")
                    if name == "disk":
                        html_parts.append(f"<tr><td>{s} Disk</td><td>{info.get('free_gb','?')}GB free / {info.get('total_gb','?')}GB ({info.get('used_pct','?')}% used)</td></tr>")
                    elif name == "memory":
                        html_parts.append(f"<tr><td>{s} Memory</td><td>{info.get('available_mb','?')}MB free / {info.get('total_mb','?')}MB ({info.get('used_pct','?')}% used)</td></tr>")
                    elif name == "load":
                        html_parts.append(f"<tr><td>{s} Load</td><td>{info.get('load_1m','?')} / {info.get('load_5m','?')} / {info.get('load_15m','?')} ({info.get('cpu_count','?')} CPUs)</td></tr>")
                html_parts.append("</table></div>")
            html_parts.append("<footer><a href='/health'>JSON</a> | <a href='/metrics'>Prometheus</a> | Auto-refresh: 30s</footer>")
            html_parts.append("<script>setTimeout(()=>location.reload(),30000)</script>")
            html_parts.append("</body></html>")
            html = "\n".join(html_parts)
            _send_html_util(self, html)

        def log_message(self, format, *args):
            print(f"[HealthCheck] {args[0]}")

    server = HTTPServer((host, port), HealthHandler)
    print(f"🏥 Health Check HTTP server on http://{host}:{port}")
    print(f"   Endpoints: /health (JSON) | /metrics (Prometheus) | / (Dashboard)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Health Check server stopped")
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="OnePersonCo Health Check")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--prometheus", action="store_true",
                        help="Prometheus exposition format output")
    parser.add_argument("--alert", action="store_true", help="Send alert on failure")
    parser.add_argument("--serve", action="store_true",
                        help="Run as HTTP server (expose /health, /metrics, /)")
    parser.add_argument("--port", type=int, default=9100,
                        help="HTTP server port (default: 9100, used with --serve)")
    parser.add_argument("--host", default="0.0.0.0",
                        help="HTTP server host (default: 0.0.0.0, used with --serve)")
    args = parser.parse_args()

    if args.serve:
        serve_http(port=args.port, host=args.host)
        return

    results = run_checks()

    if args.json:
        print(json.dumps(results, indent=2))
    elif args.prometheus:
        print(format_prometheus(results))
    else:
        print_report(results)

    if args.alert and results["overall"] != "healthy":
        # TODO: 发送飞书/Telegram告警
        print("⚠️ Alert: system is not healthy!")

    sys.exit(0 if results["overall"] == "healthy" else 1)


if __name__ == "__main__":
    main()
