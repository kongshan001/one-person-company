#!/usr/bin/env python3
"""
PingBot - 网站/API 可用性监控
零依赖，纯 Python 标准库

用法:
  python monitor.py [--port 8081] [--host 0.0.0.0]

API:
  POST /api/check          - 立即检查一个URL
  GET  /api/status         - 所有目标状态
  GET  /api/history/{name} - 某个目标的历史
  POST /api/targets        - 添加监控目标
  DELETE /api/targets/{name} - 删除监控目标
  PUT  /api/targets/{name}/pause  - 暂停监控（维护窗口）
  PUT  /api/targets/{name}/resume - 恢复监控
  GET  /health             - 健康检查
"""

import argparse
import json
import os
import re
import sqlite3
import time
import urllib.request
import urllib.error
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from pathlib import Path
from threading import Thread
import threading

# 引入集中配置与共享工具
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import PingBotConfig
from utils import send_cors_headers, handle_options, send_json, send_html, parse_body


# ============ 配置（引用集中配置） ============

DB_PATH = PingBotConfig.DB_PATH
CHECK_INTERVAL = PingBotConfig.CHECK_INTERVAL
REQUEST_TIMEOUT = PingBotConfig.REQUEST_TIMEOUT
MAX_HISTORY_DAYS = PingBotConfig.MAX_HISTORY_DAYS
MAX_BODY_READ = PingBotConfig.MAX_BODY_READ

ALERT_WEBHOOK_URL = PingBotConfig.ALERT_WEBHOOK_URL


# ============ 告警通知 ============

# 告警节流：每个 target 的最近告警时间，防止告警风暴
_alert_cooldown_seconds = 300  # 默认5分钟冷却
_last_alert_time: dict = {}  # {target_name: timestamp}


def send_alert(target_name: str, url: str, error: str, cooldown: int = None) -> bool:
    """POST JSON 告警到 webhook URL，支持冷却期节流

    同一 target 在冷却期内不会重复发送告警，防止告警风暴。

    Args:
        target_name: 目标名称
        url: 目标 URL
        error: 错误信息
        cooldown: 冷却秒数，默认使用 _alert_cooldown_seconds

    Returns:
        True 表示告警已发送，False 表示被节流跳过
    """
    if not ALERT_WEBHOOK_URL:
        return False

    # 冷却期检查
    if cooldown is None:
        cooldown = _alert_cooldown_seconds
    now = time.time()
    last = _last_alert_time.get(target_name, 0)
    if now - last < cooldown:
        return False  # 冷却期内，跳过

    try:
        payload = json.dumps({
            "alert": "service_down",
            "target": target_name,
            "url": url,
            "error": error,
            "timestamp": datetime.utcnow().isoformat(),
        }).encode()
        req = urllib.request.Request(
            ALERT_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10):
            pass
        _last_alert_time[target_name] = now
        return True
    except Exception as e:
        print(f"[PingBot] Alert webhook failed: {e}")
        return False


def set_alert_cooldown(seconds: int):
    """设置告警冷却时间（秒）

    Args:
        seconds: 冷却秒数，最小60秒
    """
    global _alert_cooldown_seconds
    _alert_cooldown_seconds = max(60, seconds)


def reset_alert_cooldown(target_name: str = None):
    """重置告警冷却计时器

    Args:
        target_name: 指定目标名称，None 则重置全部
    """
    if target_name:
        _last_alert_time.pop(target_name, None)
    else:
        _last_alert_time.clear()


# ============ 数据库 ============

class PingDB:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.Lock()
        self._init_tables()
    
    def _init_tables(self):
        with self.lock:
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS targets (
                    name TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    method TEXT DEFAULT 'GET',
                    expected_status INTEGER DEFAULT 200,
                    expected_keyword TEXT,
                    interval INTEGER DEFAULT 60,
                    enabled INTEGER DEFAULT 1,
                    created_at TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_name TEXT NOT NULL,
                    status_code INTEGER,
                    response_time_ms INTEGER,
                    is_up INTEGER,
                    error TEXT,
                    checked_at TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (target_name) REFERENCES targets(name)
                );
                CREATE INDEX IF NOT EXISTS idx_checks_target ON checks(target_name);
                CREATE INDEX IF NOT EXISTS idx_checks_time ON checks(checked_at);
            """)
            self.conn.commit()
    
    def add_target(self, name: str, url: str, method: str = "GET",
                   expected_status: int = 200, expected_keyword: str = None,
                   interval: int = 60) -> dict:
        # Validate name: only [a-zA-Z0-9_-]
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', name):
            return {"error": "name must contain only alphanumeric characters, underscores, and hyphens"}
        # Validate url: must start with http:// or https://
        if not url.startswith("http://") and not url.startswith("https://"):
            return {"error": "url must start with http:// or https://"}
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO targets (name, url, method, expected_status, expected_keyword, interval) VALUES (?, ?, ?, ?, ?, ?)",
                (name, url, method, expected_status, expected_keyword, interval)
            )
            self.conn.commit()
        return {"name": name, "url": url, "method": method}
    
    def remove_target(self, name: str) -> bool:
        with self.lock:
            cursor = self.conn.execute("DELETE FROM targets WHERE name = ?", (name,))
            self.conn.commit()
            return cursor.rowcount > 0

    def pause_target(self, name: str) -> dict:
        """暂停监控目标（设置 enabled=0），用于维护窗口"""
        with self.lock:
            cursor = self.conn.execute(
                "UPDATE targets SET enabled = 0 WHERE name = ?", (name,)
            )
            self.conn.commit()
            if cursor.rowcount == 0:
                return {"error": "Target not found"}
            return {"name": name, "enabled": False, "action": "paused"}

    def resume_target(self, name: str) -> dict:
        """恢复监控目标（设置 enabled=1）"""
        with self.lock:
            cursor = self.conn.execute(
                "UPDATE targets SET enabled = 1 WHERE name = ?", (name,)
            )
            self.conn.commit()
            if cursor.rowcount == 0:
                return {"error": "Target not found"}
            return {"name": name, "enabled": True, "action": "resumed"}
    
    def get_targets(self, enabled_only: bool = False) -> list:
        query = "SELECT * FROM targets"
        if enabled_only:
            query += " WHERE enabled = 1"
        with self.lock:
            rows = self.conn.execute(query).fetchall()
        return [dict(r) for r in rows]
    
    def record_check(self, target_name: str, status_code: int = None,
                     response_time_ms: int = None, is_up: bool = False,
                     error: str = None):
        with self.lock:
            self.conn.execute(
                "INSERT INTO checks (target_name, status_code, response_time_ms, is_up, error) VALUES (?, ?, ?, ?, ?)",
                (target_name, status_code, response_time_ms, int(is_up), error)
            )
            self.conn.commit()
    
    def get_history(self, target_name: str, hours: int = 24) -> list:
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM checks WHERE target_name = ? AND checked_at > datetime('now', ?) ORDER BY checked_at DESC LIMIT 500",
                (target_name, f"-{hours} hours")
            ).fetchall()
        return [dict(r) for r in rows]
    
    def get_status(self) -> list:
        """获取所有启用目标的状态，含可用率和响应时间百分位统计"""
        targets = self.get_targets(enabled_only=True)
        result = []
        for t in targets:
            with self.lock:
                last = self.conn.execute(
                    "SELECT * FROM checks WHERE target_name = ? ORDER BY checked_at DESC LIMIT 1",
                    (t["name"],)
                ).fetchone()
            
            # 计算可用率 (最近24小时)
            with self.lock:
                stats = self.conn.execute(
                    "SELECT COUNT(*) as total, SUM(is_up) as up_count FROM checks WHERE target_name = ? AND checked_at > datetime('now', '-24 hours')",
                    (t["name"],)
                ).fetchone()
            
            uptime_pct = (stats["up_count"] / stats["total"] * 100) if stats["total"] else 0

            # 响应时间百分位统计 (最近24小时)
            latency_stats = self._get_latency_stats(t["name"])

            result.append({
                **t,
                "last_check": dict(last) if last else None,
                "uptime_24h": round(uptime_pct, 2),
                "total_checks_24h": stats["total"],
                "latency_24h": latency_stats,
            })
        return result

    def _get_latency_stats(self, target_name: str) -> dict:
        """计算目标最近24小时的响应时间百分位数

        Args:
            target_name: 监控目标名称

        Returns:
            包含 avg, p50, p95, p99 的字典
        """
        with self.lock:
            rows = self.conn.execute(
                "SELECT response_time_ms FROM checks WHERE target_name = ? AND is_up = 1 AND response_time_ms IS NOT NULL AND checked_at > datetime('now', '-24 hours')",
                (target_name,)
            ).fetchall()

        values = [r["response_time_ms"] for r in rows if r["response_time_ms"] is not None]
        if not values:
            return {"avg": None, "p50": None, "p95": None, "p99": None}

        sorted_vals = sorted(values)
        n = len(sorted_vals)
        avg = round(sum(sorted_vals) / n)
        p50 = sorted_vals[int(n * 0.50)]
        p95 = sorted_vals[min(int(n * 0.95), n - 1)]
        p99 = sorted_vals[min(int(n * 0.99), n - 1)]

        return {"avg": avg, "p50": p50, "p95": p95, "p99": p99}
    
    def cleanup_old(self):
        """清理旧记录（参数化查询）"""
        with self.lock:
            self.conn.execute(
                "DELETE FROM checks WHERE checked_at < datetime('now', ? || ' days')",
                (str(-MAX_HISTORY_DAYS),)
            )
            self.conn.commit()


# ============ 检查器 ============

class Pinger:
    def __init__(self, db: PingDB):
        self.db = db
        self.running = False
    
    def check_url(self, url: str, method: str = "GET",
                  expected_status: int = 200,
                  expected_keyword: str = None) -> dict:
        """检查单个URL，只读取前 64KB 响应体"""
        start = time.time()
        try:
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                status_code = resp.status
                body = resp.read(MAX_BODY_READ).decode("utf-8", errors="ignore")
                response_time = int((time.time() - start) * 1000)
                
                is_up = (status_code == expected_status)
                if expected_keyword and expected_keyword not in body:
                    is_up = False
                
                return {
                    "status_code": status_code,
                    "response_time_ms": response_time,
                    "is_up": is_up,
                    "error": None,
                }
        except urllib.error.HTTPError as e:
            response_time = int((time.time() - start) * 1000)
            return {
                "status_code": e.code,
                "response_time_ms": response_time,
                "is_up": e.code == expected_status,
                "error": str(e),
            }
        except Exception as e:
            response_time = int((time.time() - start) * 1000)
            return {
                "status_code": None,
                "response_time_ms": response_time,
                "is_up": False,
                "error": str(e),
            }
    
    def check_all(self):
        """检查所有启用的目标"""
        targets = self.db.get_targets(enabled_only=True)
        for t in targets:
            result = self.check_url(
                t["url"], t["method"], t["expected_status"], t["expected_keyword"]
            )
            self.db.record_check(t["name"], **result)
            # 服务 down 时发送告警（受冷却期节流）
            if not result["is_up"] and result.get("error"):
                send_alert(t["name"], t["url"], result["error"])
            elif result["is_up"]:
                # 服务恢复时重置该目标的告警冷却，确保下次 down 时能立即告警
                reset_alert_cooldown(t["name"])
    
    def start_loop(self):
        """后台循环检查"""
        self.running = True
        while self.running:
            try:
                self.check_all()
            except Exception as e:
                print(f"[PingBot] check_all error: {e}")
            time.sleep(CHECK_INTERVAL)


# ============ HTTP 服务 ============

db = None
pinger = None


class PingHandler(BaseHTTPRequestHandler):
    
    API_KEY = PingBotConfig.API_KEY
    
    def _check_auth(self) -> bool:
        """Check API key for POST/DELETE. Skip if no key configured."""
        if not self.API_KEY:
            return True
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:] == self.API_KEY
        return False
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests."""
        handle_options(self, allowed_headers="Content-Type, Authorization")
    
    def _send_json(self, data, status=200):
        send_json(self, data, status)
    
    def _read_body(self):
        return parse_body(self)
    
    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        
        if path == "/health":
            self._send_json({"status": "ok", "targets": len(db.get_targets())})
        elif path == "/api/status":
            self._send_json({"targets": db.get_status()})
        elif path.startswith("/api/history/"):
            name = path[14:]
            history = db.get_history(name)
            self._send_json({"target": name, "checks": history})
        elif path == "/":
            self._send_dashboard()
        else:
            self._send_json({"error": "Not found"}, 404)
    
    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        
        if not self._check_auth():
            self._send_json({"error": "Unauthorized"}, 401)
            return
        
        if path == "/api/check":
            data = self._read_body()
            if data is None:
                self._send_json({"error": "Invalid JSON body"}, 400)
                return
            url = data.get("url", "")
            if not url.startswith("http://") and not url.startswith("https://"):
                self._send_json({"error": "url must start with http:// or https://"}, 400)
                return
            result = pinger.check_url(
                url,
                data.get("method", "GET"),
                data.get("expected_status", 200),
                data.get("expected_keyword"),
            )
            self._send_json(result)
        elif path == "/api/targets":
            data = self._read_body()
            if data is None:
                self._send_json({"error": "Invalid JSON body"}, 400)
                return
            required = ["name", "url"]
            if not all(data.get(k) for k in required):
                self._send_json({"error": "name and url required"}, 400)
                return
            result = db.add_target(
                data["name"], data["url"],
                data.get("method", "GET"),
                data.get("expected_status", 200),
                data.get("expected_keyword"),
                data.get("interval", 60),
            )
            if "error" in result:
                self._send_json(result, 400)
            else:
                self._send_json(result, 201)
        else:
            self._send_json({"error": "Not found"}, 404)
    
    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path

        if not self._check_auth():
            self._send_json({"error": "Unauthorized"}, 401)
            return

        if path.startswith("/api/targets/"):
            name = path[14:]
            if db.remove_target(name):
                self._send_json({"deleted": name})
            else:
                self._send_json({"error": "Not found"}, 404)

    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path

        if not self._check_auth():
            self._send_json({"error": "Unauthorized"}, 401)
            return

        if path.endswith("/pause"):
            name = path[len("/api/targets/"):-len("/pause")]
            result = db.pause_target(name)
            if "error" in result:
                self._send_json(result, 404)
            else:
                self._send_json(result)
        elif path.endswith("/resume"):
            name = path[len("/api/targets/"):-len("/resume")]
            result = db.resume_target(name)
            if "error" in result:
                self._send_json(result, 404)
            else:
                self._send_json(result)
        else:
            self._send_json({"error": "Not found"}, 404)
    
    def _send_dashboard(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        send_cors_headers(self, allowed_headers="Content-Type, Authorization")
        self.end_headers()
        # 简洁监控面板
        html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>PingBot</title>
<style>
body{font-family:system-ui;background:#1a1a2e;color:#eee;max-width:900px;margin:40px auto;padding:20px}
h1{color:#e94560}.up{color:#2ecc71}.down{color:#e74c3c}
.target{background:#16213e;padding:16px;margin:8px 0;border-radius:8px;display:flex;justify-content:space-between;align-items:center}
.dot{width:12px;height:12px;border-radius:50%;display:inline-block;margin-right:8px}
.dot.up{background:#2ecc71}.dot.down{background:#e74c3c}
form{background:#16213e;padding:16px;border-radius:8px;margin-top:24px}
input{background:#0f3460;color:#eee;border:1px solid #333;padding:8px;margin:4px;border-radius:4px}
button{background:#e94560;color:#fff;border:none;padding:8px 16px;border-radius:4px;cursor:pointer}
</style></head><body>
<h1>🤖 PingBot</h1><div id="targets">Loading...</div>
<form id="f">
<h3>+ Add Target</h3>
<input id="n" placeholder="Name" required><input id="u" placeholder="URL" required>
<input id="s" placeholder="Expected Status" value="200" type="number">
<button type="submit">Add</button>
</form>
<script>
const load=()=>fetch('/api/status').then(r=>r.json()).then(d=>{
document.getElementById('targets').innerHTML=d.targets.map(t=>{
const last=t.last_check;const up=last?last.is_up:null;
const lat=t.latency_24h||{};const latStr=lat.p50?(' | Latency: P50 '+lat.p50+'ms / P95 '+lat.p95+'ms / P99 '+lat.p99+'ms'):'';
return '<div class="target"><div><span class="dot '+(up?'up':'down')+'"></span><strong>'+t.name+'</strong> <small>'+t.url+'</small></div><div>'+(last?'<span class="'+(up?'up':'down')+'">'+(up?'UP':'DOWN')+'</span> '+last.response_time_ms+'ms':'—')+' | Uptime: '+t.uptime_24h+'%'+latStr+'</div></div>';
}).join('')||'<p>No targets yet</p>';
});
document.getElementById('f').onsubmit=async e=>{e.preventDefault();const d={name:document.getElementById('n').value,url:document.getElementById('u').value,expected_status:parseInt(document.getElementById('s').value)};await fetch('/api/targets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});load()};
load();setInterval(load,30000);
</script></body></html>"""
        self.wfile.write(html.encode())
    
    def log_message(self, format, *args):
        print(f"[PingBot] {args[0]}")


# ============ 入口 ============

def main():
    parser = argparse.ArgumentParser(description="PingBot - Uptime Monitor")
    parser.add_argument("--port", type=int, default=PingBotConfig.DEFAULT_PORT)
    parser.add_argument("--host", default=PingBotConfig.DEFAULT_HOST)
    parser.add_argument("--db", default=DB_PATH)
    args = parser.parse_args()
    
    global db, pinger
    db = PingDB(args.db)
    pinger = Pinger(db)
    
    # 启动后台检查线程
    checker_thread = Thread(target=pinger.start_loop, daemon=True)
    checker_thread.start()
    
    server = HTTPServer((args.host, args.port), PingHandler)
    print(f"🤖 PingBot running on http://{args.host}:{args.port}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pinger.running = False
        print("\n👋 PingBot stopped")
        server.server_close()


if __name__ == "__main__":
    main()
