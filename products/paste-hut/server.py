#!/usr/bin/env python3
"""
PasteHut - 极简 Pastebin 服务
零依赖，纯 Python 标准库

用法:
  python server.py [--port 9292] [--host 0.0.0.0]
"""

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Thread, Lock

# 引入集中配置与共享工具
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import PasteHutConfig
from utils import send_cors_headers, handle_options, send_json, send_html, send_text, sanitize_id


# ============ 配置（引用集中配置） ============

DATA_DIR = PasteHutConfig.DATA_DIR
MAX_PASTE_SIZE = PasteHutConfig.MAX_PASTE_SIZE
DEFAULT_EXPIRY_HOURS = PasteHutConfig.DEFAULT_EXPIRY_HOURS
MAX_EXPIRY_HOURS = PasteHutConfig.MAX_EXPIRY_HOURS
RATE_LIMIT_WINDOW = PasteHutConfig.RATE_LIMIT_WINDOW
RATE_LIMIT_MAX = PasteHutConfig.RATE_LIMIT_MAX

ALLOWED_SYNTAXES = PasteHutConfig.ALLOWED_SYNTAXES

# Views flush 配置
VIEWS_FLUSH_INTERVAL = PasteHutConfig.VIEWS_FLUSH_INTERVAL
VIEWS_FLUSH_SECONDS = PasteHutConfig.VIEWS_FLUSH_SECONDS


# ============ 存储 ============

class PasteStore:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.meta_file = self.data_dir / "meta.json"
        self.meta = self._load_meta()
        self.rate_limits = {}  # ip -> [timestamps]
        # 延迟批量写入 views 相关
        self._views_dirty = {}  # paste_id -> pending view count
        self._views_total_dirty = 0
        self._last_flush = time.time()
        self._flush_lock = Lock()
    
    def _load_meta(self) -> dict:
        if self.meta_file.exists():
            try:
                return json.loads(self.meta_file.read_text())
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    def _save_meta(self):
        """保存 meta 到磁盘（带文件锁）"""
        self.meta_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = str(self.meta_file) + ".tmp"
        with open(tmp_path, "w") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(self.meta, f, indent=2, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        os.replace(tmp_path, str(self.meta_file))
    
    def _flush_views(self):
        """将内存中的 views 增量写入 meta 并持久化"""
        with self._flush_lock:
            if not self._views_dirty:
                return
            for paste_id, delta in self._views_dirty.items():
                if paste_id in self.meta:
                    self.meta[paste_id]["views"] = self.meta[paste_id].get("views", 0) + delta
            self._views_dirty.clear()
            self._views_total_dirty = 0
            self._last_flush = time.time()
            self._save_meta()
    
    def _maybe_flush_views(self):
        """检查是否需要 flush views"""
        should_flush = (
            self._views_total_dirty >= VIEWS_FLUSH_INTERVAL or
            (time.time() - self._last_flush) >= VIEWS_FLUSH_SECONDS
        )
        if should_flush:
            self._flush_views()
    
    def _generate_id(self, content: str) -> str:
        """生成短ID: 8位hash"""
        return hashlib.sha256(content.encode()).hexdigest()[:8]
    
    def check_rate_limit(self, ip: str) -> bool:
        """检查速率限制"""
        now = time.time()
        if ip not in self.rate_limits:
            self.rate_limits[ip] = []
        
        # 清理过期记录
        self.rate_limits[ip] = [t for t in self.rate_limits[ip] if now - t < RATE_LIMIT_WINDOW]
        
        if len(self.rate_limits[ip]) >= RATE_LIMIT_MAX:
            return False
        
        self.rate_limits[ip].append(now)
        return True
    
    @staticmethod
    def _hash_password(password: str) -> str:
        """对密码进行 SHA-256 哈希（加盐）"""
        salt = "pastehut_salt_2024"
        return hashlib.sha256((salt + password).encode()).hexdigest()
    
    def create(self, content: str, title: str = "", syntax: str = "text",
               expiry_hours: int = None, ip: str = "unknown",
               burn_after_read: bool = False, password: str = "") -> dict:
        """创建 paste
        
        Args:
            content: 粘贴内容
            title: 标题（可选）
            syntax: 语法高亮类型
            expiry_hours: 过期时间（小时）
            ip: 创建者 IP
            burn_after_read: 阅后即焚，首次查看后自动删除
            password: 访问密码（可选，空字符串表示无密码）
        
        Returns:
            创建结果字典，含 id、delete_key 等；失败时含 error
        """
        if len(content) > MAX_PASTE_SIZE:
            return {"error": f"内容超过限制 ({MAX_PASTE_SIZE // 1024}KB)"}
        
        if expiry_hours is None:
            expiry_hours = DEFAULT_EXPIRY_HOURS
        
        # 校验 expiry_hours
        try:
            expiry_hours = int(expiry_hours)
        except (TypeError, ValueError):
            return {"error": f"expiry_hours 必须为整数"}
        if not (0 < expiry_hours <= MAX_EXPIRY_HOURS):
            return {"error": f"expiry_hours 必须在 1~{MAX_EXPIRY_HOURS} 之间"}
        
        # 校验 syntax
        if syntax not in ALLOWED_SYNTAXES:
            return {"error": f"syntax 不合法，允许值: {', '.join(sorted(ALLOWED_SYNTAXES))}"}
        
        paste_id = self._generate_id(content + str(time.time()))
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=expiry_hours)
        
        # 生成 delete_key
        delete_key = secrets.token_urlsafe(16)
        
        # 保存内容
        paste_file = self.data_dir / f"{paste_id}.txt"
        paste_file.write_text(content)
        
        # 处理密码哈希
        password_hash = ""
        has_password = False
        if password and password.strip():
            password_hash = self._hash_password(password.strip())
            has_password = True
        
        # 保存元数据
        self.meta[paste_id] = {
            "id": paste_id,
            "title": title or f"Untitled {paste_id[:4]}",
            "syntax": syntax,
            "size": len(content),
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "ip": ip,
            "views": 0,
            "delete_key": delete_key,
            "burn_after_read": burn_after_read,
            "has_password": has_password,
            "password_hash": password_hash,
        }
        self._save_meta()
        
        result = dict(self.meta[paste_id])
        result["delete_key"] = delete_key  # 创建时返回 delete_key
        # 不返回密码哈希给客户端
        result.pop("password_hash", None)
        return result
    
    def get(self, paste_id: str, password: str = "") -> dict:
        """获取 paste（views 使用延迟批量写入）
        
        Args:
            paste_id: 粘贴 ID
            password: 访问密码（如果有密码保护则必填）
        
        Returns:
            粘贴内容字典，不存在或密码错误返回 None
        """
        if paste_id not in self.meta:
            return None
        
        meta = self.meta[paste_id]
        
        # 检查过期
        expires_at = datetime.fromisoformat(meta["expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            self.delete(paste_id)
            return None
        
        # 密码验证
        if meta.get("has_password"):
            if not password or not password.strip():
                return {"error": "password_required", "message": "此粘贴需要密码访问"}
            if self._hash_password(password.strip()) != meta.get("password_hash", ""):
                return {"error": "wrong_password", "message": "密码错误"}
        
        # 读取内容
        paste_file = self.data_dir / f"{paste_id}.txt"
        if not paste_file.exists():
            return None
        
        # 延迟递增 views
        with self._flush_lock:
            self._views_dirty[paste_id] = self._views_dirty.get(paste_id, 0) + 1
            self._views_total_dirty += 1
        
        # 返回时包含当前总 views
        current_views = meta.get("views", 0) + self._views_dirty.get(paste_id, 0)
        
        result = dict(meta)
        result["content"] = paste_file.read_text()
        result["views"] = current_views
        # 不返回密码哈希
        result.pop("password_hash", None)
        
        # 阅后即焚：首次查看后自动删除
        if meta.get("burn_after_read"):
            # 先 flush views 以确保数据完整
            self._flush_views()
            self.delete(paste_id)
            result["_burned"] = True  # 标记已焚毁，前端可提示
        
        self._maybe_flush_views()
        
        return result
    
    def delete(self, paste_id: str) -> bool:
        """删除 paste"""
        if paste_id in self.meta:
            paste_file = self.data_dir / f"{paste_id}.txt"
            if paste_file.exists():
                paste_file.unlink()
            del self.meta[paste_id]
            # 清除脏 views
            with self._flush_lock:
                self._views_dirty.pop(paste_id, None)
            self._save_meta()
            return True
        return False
    
    def delete_with_key(self, paste_id: str, delete_key: str) -> dict:
        """通过 delete_key 鉴权删除 paste"""
        if paste_id not in self.meta:
            return {"error": "Not found"}
        meta = self.meta[paste_id]
        if meta.get("delete_key") != delete_key:
            return {"error": "Invalid delete_key"}
        self.delete(paste_id)
        return {"deleted": paste_id}
    
    def cleanup_expired(self) -> int:
        """清理过期 paste"""
        now = datetime.now(timezone.utc)
        expired = []
        for pid, meta in self.meta.items():
            expires_at = datetime.fromisoformat(meta["expires_at"])
            if now > expires_at:
                expired.append(pid)
        
        for pid in expired:
            self.delete(pid)
        
        return len(expired)
    
    def list_recent(self, limit: int = 20, query: str = "") -> list:
        """列出最近的 paste（不含敏感字段）

        Args:
            limit: 返回数量上限
            query: 搜索关键词，匹配标题（不区分大小写），为空则不过滤

        Returns:
            安全字段列表
        """
        pastes = sorted(
            self.meta.values(),
            key=lambda x: x["created_at"],
            reverse=True,
        )
        # 搜索过滤
        if query and query.strip():
            q = query.strip().lower()
            pastes = [p for p in pastes if q in p.get("title", "").lower()]
        # 过滤敏感字段
        safe_fields = {"id", "title", "syntax", "size", "created_at", "expires_at", "views", "burn_after_read", "has_password"}
        result = []
        for p in pastes[:limit]:
            result.append({k: v for k, v in p.items() if k in safe_fields})
        return result


# ============ HTTP 服务 ============

store = None  # 全局 store 实例


class PasteHandler(BaseHTTPRequestHandler):
    
    def do_OPTIONS(self):
        """处理 CORS 预检请求"""
        handle_options(self)
    
    def _send_json(self, data, status=200):
        send_json(self, data, status)
    
    def _send_html(self, html, status=200):
        send_html(self, html, status)
    
    def _send_text(self, text, status=200):
        send_text(self, text, status)
    
    def do_GET(self):
        path = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(path.query)
        password = params.get("password", [""])[0]
        
        if path.path == "/" or path.path == "":
            # 首页 - 创建表单
            self._send_html(self._render_home())
        elif path.path == "/health":
            self._send_json({"status": "ok", "pastes": len(store.meta)})
        elif path.path == "/api/list":
            query = params.get("q", [""])[0]
            pastes = store.list_recent(query=query)
            self._send_json({"pastes": pastes})
        elif path.path.startswith("/raw/"):
            paste_id = path.path[5:]
            if not sanitize_id(paste_id):
                self._send_json({"error": "Invalid paste ID"}, 400)
                return
            paste = store.get(paste_id, password=password)
            if paste is None:
                self._send_json({"error": "Not found"}, 404)
            elif isinstance(paste, dict) and paste.get("error") == "password_required":
                self._send_json({"error": "Password required"}, 401)
            elif isinstance(paste, dict) and paste.get("error") == "wrong_password":
                self._send_json({"error": "Wrong password"}, 403)
            else:
                self._send_text(paste["content"])
        elif path.path.startswith("/"):
            paste_id = path.path[1:]
            # 跳过静态资源路径
            if paste_id and sanitize_id(paste_id):
                paste = store.get(paste_id, password=password)
                if paste is None:
                    self._send_html(self._render_404(), 404)
                elif isinstance(paste, dict) and paste.get("error") == "password_required":
                    self._send_html(self._render_password_prompt(paste_id), 401)
                elif isinstance(paste, dict) and paste.get("error") == "wrong_password":
                    self._send_html(self._render_password_prompt(paste_id, wrong=True), 403)
                else:
                    self._send_html(self._render_paste(paste))
            else:
                self._send_html(self._render_404(), 404)
    
    def do_POST(self):
        path = urllib.parse.urlparse(self.path)
        
        if path.path != "/api/create":
            self._send_json({"error": "Not found"}, 404)
            return
        
        # 速率限制
        ip = self.client_address[0]
        if not store.check_rate_limit(ip):
            self._send_json({"error": "Rate limit exceeded"}, 429)
            return
        
        # 读取请求体
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            # 尝试 form data
            params = urllib.parse.parse_qs(body)
            data = {k: v[0] for k, v in params.items()}
        
        content = data.get("content", "")
        if not content:
            self._send_json({"error": "内容不能为空"}, 400)
            return
        
        result = store.create(
            content=content,
            title=data.get("title", ""),
            syntax=data.get("syntax", "text"),
            expiry_hours=int(data.get("expiry_hours", DEFAULT_EXPIRY_HOURS)),
            ip=ip,
            burn_after_read=bool(data.get("burn_after_read", False)),
            password=data.get("password", ""),
        )
        
        if "error" in result:
            self._send_json(result, 400)
        else:
            self._send_json(result, 201)
    
    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path)
        
        # DELETE /api/paste/{id}
        if path.path.startswith("/api/paste/"):
            paste_id = path.path[len("/api/paste/"):]
            # 输入校验：paste_id 必须是十六进制
            if not sanitize_id(paste_id):
                self._send_json({"error": "Invalid paste ID"}, 400)
                return
            # 从 query string 或 header 获取 delete_key
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            delete_key = params.get("delete_key", [None])[0]
            if not delete_key:
                delete_key = self.headers.get("X-Delete-Key", "")
            if not delete_key:
                self._send_json({"error": "delete_key required (query param or X-Delete-Key header)"}, 400)
                return
            result = store.delete_with_key(paste_id, delete_key)
            if "error" in result:
                self._send_json(result, 403 if "Invalid" in result.get("error", "") else 404)
            else:
                self._send_json(result)
        else:
            self._send_json({"error": "Not found"}, 404)
    
    def _render_home(self):
        return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>PasteHut</title>
<style>
body{font-family:monospace;background:#1a1a2e;color:#eee;max-width:800px;margin:40px auto;padding:20px}
h1{color:#e94560}textarea{width:100%;height:300px;background:#16213e;color:#eee;border:1px solid #333;padding:12px;font-family:monospace;font-size:14px;border-radius:4px}
input,select{background:#16213e;color:#eee;border:1px solid #333;padding:8px;margin:4px;border-radius:4px}
button{background:#e94560;color:#fff;border:none;padding:10px 24px;font-size:16px;border-radius:4px;cursor:pointer}
button:hover{background:#c81e45}a{color:#0f3460}
.recent{margin-top:30px}.recent a{color:#e94560;text-decoration:none}
</style></head><body>
<h1>📋 PasteHut</h1>
<p>Minimal pastebin. No signup, no tracking.</p>
<form id="f">
<textarea id="c" name="content" placeholder="Paste your code here..."></textarea><br>
<input id="t" name="title" placeholder="Title (optional)">
<select id="s" name="syntax"><option value="text">Plain Text</option><option value="python">Python</option><option value="javascript">JavaScript</option><option value="html">HTML</option><option value="css">CSS</option><option value="json">JSON</option><option value="sql">SQL</option><option value="bash">Bash</option></select>
<select id="e" name="expiry_hours"><option value="24">24 hours</option><option value="168" selected>7 days</option><option value="720">30 days</option></select>
<label style="cursor:pointer"><input type="checkbox" id="bar" name="burn_after_read"> 🔥 Burn after read</label>
<input id="pw" name="password" type="password" placeholder="Password (optional)">
<button type="submit">🚀 Create Paste</button>
</form>
<div id="r" class="recent"></div>
<script>
document.getElementById('f').onsubmit=async(e)=>{
e.preventDefault();
const d={content:document.getElementById('c').value,title:document.getElementById('t').value,syntax:document.getElementById('s').value,expiry_hours:document.getElementById('e').value,burn_after_read:document.getElementById('bar').checked,password:document.getElementById('pw').value};
const res=await fetch('/api/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
const j=await res.json();if(j.id){if(j.delete_key){console.log('Delete key:',j.delete_key);}location.href='/'+j.id;}else alert(j.error||'Error');
};
const loadList=(q)=>{const url=q?'/api/list?q='+encodeURIComponent(q):'/api/list';fetch(url).then(r=>r.json()).then(d=>{
const el=document.getElementById('r');
if(d.pastes&&d.pastes.length){el.innerHTML='<h3>Recent</h3><input id="sq" placeholder="🔍 Search..." value="'+(q||'').replace(/"/g,'&quot;')+'" style="background:#16213e;color:#eee;border:1px solid #333;padding:6px;border-radius:4px;margin-left:8px;width:200px">'+d.pastes.map(p=>'<div><a href="/'+p.id+'">'+p.title+'</a> <small>('+p.syntax+', '+p.size+'B)</small></div>').join('');document.getElementById('sq').oninput=function(){clearTimeout(window._st);window._st=setTimeout(()=>loadList(this.value),300);};}
});};
loadList('');
</script></body></html>"""
    
    def _render_paste(self, paste):
        import html as html_module
        escaped = html_module.escape(paste["content"])
        # 阅后即焚警告
        burn_warning = ""
        if paste.get("_burned"):
            burn_warning = '<div style="background:#c81e45;color:#fff;padding:12px;border-radius:4px;margin-bottom:16px">🔥 This was a burn-after-read paste and has been permanently deleted. Copy the content now — it won\'t be available again!</div>'
        elif paste.get("burn_after_read"):
            burn_warning = '<div style="background:#ff9800;color:#000;padding:8px;border-radius:4px;margin-bottom:16px">🔥 Burn after read — this paste will be deleted after viewing</div>'
        # 密码标识
        password_badge = ' 🔒' if paste.get("has_password") else ''
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html_module.escape(paste['title'])} - PasteHut</title>
<style>
body{{font-family:monospace;background:#1a1a2e;color:#eee;max-width:800px;margin:40px auto;padding:20px}}
h1{{color:#e94560}}.meta{{color:#666;font-size:12px;margin-bottom:20px}}
pre{{background:#16213e;padding:16px;border-radius:4px;overflow-x:auto;white-space:pre-wrap;word-break:break-all}}
a{{color:#e94560}}.actions{{margin-top:16px}}
button{{background:#16213e;color:#eee;border:1px solid #333;padding:8px 16px;border-radius:4px;cursor:pointer}}
</style></head><body>
<h1>{html_module.escape(paste['title'])}{password_badge}</h1>
{burn_warning}
<div class="meta">
  📝 {paste['syntax']} · {paste['size']}B · 👀 {paste['views']} views · 
  📅 {paste['created_at'][:10]} · ⏰ expires {paste['expires_at'][:10]}
</div>
<pre>{escaped}</pre>
<div class="actions">
  <button onclick="navigator.clipboard.writeText(document.querySelector('pre').textContent)">📋 Copy</button>
  <a href="/raw/{paste['id']}"><button>⬇️ Raw</button></a>
  <a href="/"><button>🏠 Home</button></a>
</div>
</body></html>"""
    
    def _render_password_prompt(self, paste_id: str, wrong: bool = False):
        """渲染密码输入页面"""
        error_msg = '<p style="color:#e94560">❌ 密码错误，请重试</p>' if wrong else '<p>🔒 此粘贴需要密码才能访问</p>'
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>密码验证 - PasteHut</title>
<style>
body{{font-family:monospace;background:#1a1a2e;color:#eee;text-align:center;padding:100px}}
h1{{color:#e94560}}input{{background:#16213e;color:#eee;border:1px solid #333;padding:12px;font-size:16px;border-radius:4px;width:300px}}
button{{background:#e94560;color:#fff;border:none;padding:12px 24px;font-size:16px;border-radius:4px;cursor:pointer;margin-top:12px}}
a{{color:#e94560}}
</style></head>
<body>
<h1>🔒 Password Required</h1>
{error_msg}
<form onsubmit="location.href='/{paste_id}?password='+encodeURIComponent(document.getElementById('pw').value);return false;">
<input id="pw" type="password" placeholder="Enter password..." autofocus>
<br><button type="submit">🔓 Unlock</button>
</form>
<br><a href="/">← Go home</a>
</body></html>"""
    
    def _render_404(self):
        return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>404 - PasteHut</title>
<style>body{font-family:monospace;background:#1a1a2e;color:#eee;text-align:center;padding:100px}h1{color:#e94560;font-size:48px}a{color:#e94560}</style></head>
<body><h1>404</h1><p>This paste doesn't exist or has expired.</p><a href="/">← Go home</a></body></html>"""
    
    def log_message(self, format, *args):
        print(f"[PasteHut] {args[0]}")


# ============ 过期清理线程 ============

def _cleanup_loop(store_instance: PasteStore):
    """后台线程：每 10 分钟清理过期 paste"""
    while True:
        try:
            count = store_instance.cleanup_expired()
            if count:
                print(f"[PasteHut] Cleaned up {count} expired paste(s)")
            # 同时 flush 残留 views
            store_instance._flush_views()
        except Exception as e:
            print(f"[PasteHut] Cleanup error: {e}")
        time.sleep(600)  # 10 分钟


# ============ 入口 ============

def main():
    parser = argparse.ArgumentParser(description="PasteHut - Minimal Pastebin")
    parser.add_argument("--port", type=int, default=PasteHutConfig.DEFAULT_PORT)
    parser.add_argument("--host", default=PasteHutConfig.DEFAULT_HOST)
    parser.add_argument("--data-dir", default=DATA_DIR)
    args = parser.parse_args()
    
    global store
    store = PasteStore(args.data_dir)
    
    # 启动过期清理后台线程
    cleanup_thread = Thread(target=_cleanup_loop, args=(store,), daemon=True)
    cleanup_thread.start()
    
    server = HTTPServer((args.host, args.port), PasteHandler)
    print(f"📋 PasteHut running on http://{args.host}:{args.port}")
    print(f"   Data dir: {args.data_dir}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        # 退出前 flush 残留 views
        store._flush_views()
        print("\n👋 PasteHut stopped")
        server.server_close()


if __name__ == "__main__":
    main()
