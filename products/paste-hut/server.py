#!/usr/bin/env python3
"""
PasteHut - 极简 Pastebin 服务
零依赖，纯 Python 标准库

用法:
  python server.py [--port 9292] [--host 0.0.0.0]
"""

import argparse
import hashlib
import json
import os
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timedelta
from pathlib import Path

# ============ 配置 ============

DATA_DIR = os.path.expanduser("~/.pastehut/data")
MAX_PASTE_SIZE = 512 * 1024  # 512KB
DEFAULT_EXPIRY_HOURS = 24 * 7  # 7天
MAX_EXPIRY_HOURS = 24 * 30  # 30天
RATE_LIMIT_WINDOW = 60  # 秒
RATE_LIMIT_MAX = 10  # 每分钟最多10条


# ============ 存储 ============

class PasteStore:
    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.meta_file = self.data_dir / "meta.json"
        self.meta = self._load_meta()
        self.rate_limits = {}  # ip -> [timestamps]
    
    def _load_meta(self) -> dict:
        if self.meta_file.exists():
            try:
                return json.loads(self.meta_file.read_text())
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    def _save_meta(self):
        self.meta_file.write_text(json.dumps(self.meta, indent=2, ensure_ascii=False))
    
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
    
    def create(self, content: str, title: str = "", syntax: str = "text",
               expiry_hours: int = None, ip: str = "unknown") -> dict:
        """创建 paste"""
        if len(content) > MAX_PASTE_SIZE:
            return {"error": f"内容超过限制 ({MAX_PASTE_SIZE // 1024}KB)"}
        
        if expiry_hours is None:
            expiry_hours = DEFAULT_EXPIRY_HOURS
        expiry_hours = min(expiry_hours, MAX_EXPIRY_HOURS)
        
        paste_id = self._generate_id(content + str(time.time()))
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=expiry_hours)
        
        # 保存内容
        paste_file = self.data_dir / f"{paste_id}.txt"
        paste_file.write_text(content)
        
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
        }
        self._save_meta()
        
        return self.meta[paste_id]
    
    def get(self, paste_id: str) -> dict:
        """获取 paste"""
        if paste_id not in self.meta:
            return None
        
        meta = self.meta[paste_id]
        
        # 检查过期
        expires_at = datetime.fromisoformat(meta["expires_at"])
        if datetime.utcnow() > expires_at:
            self.delete(paste_id)
            return None
        
        # 读取内容
        paste_file = self.data_dir / f"{paste_id}.txt"
        if not paste_file.exists():
            return None
        
        meta["views"] += 1
        meta["content"] = paste_file.read_text()
        self._save_meta()
        
        return meta
    
    def delete(self, paste_id: str) -> bool:
        """删除 paste"""
        if paste_id in self.meta:
            paste_file = self.data_dir / f"{paste_id}.txt"
            if paste_file.exists():
                paste_file.unlink()
            del self.meta[paste_id]
            self._save_meta()
            return True
        return False
    
    def cleanup_expired(self) -> int:
        """清理过期 paste"""
        now = datetime.utcnow()
        expired = []
        for pid, meta in self.meta.items():
            expires_at = datetime.fromisoformat(meta["expires_at"])
            if now > expires_at:
                expired.append(pid)
        
        for pid in expired:
            self.delete(pid)
        
        return len(expired)
    
    def list_recent(self, limit: int = 20) -> list:
        """列出最近的 paste"""
        pastes = sorted(
            self.meta.values(),
            key=lambda x: x["created_at"],
            reverse=True,
        )
        return pastes[:limit]


# ============ HTTP 服务 ============

store = None  # 全局 store 实例


class PasteHandler(BaseHTTPRequestHandler):
    
    def _send_json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
    
    def _send_html(self, html, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())
    
    def _send_text(self, text, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(text.encode())
    
    def do_GET(self):
        path = urllib.parse.urlparse(self.path)
        
        if path.path == "/" or path.path == "":
            # 首页 - 创建表单
            self._send_html(self._render_home())
        elif path.path == "/health":
            self._send_json({"status": "ok", "pastes": len(store.meta)})
        elif path.path == "/api/list":
            pastes = store.list_recent()
            self._send_json({"pastes": pastes})
        elif path.path.startswith("/raw/"):
            paste_id = path.path[5:]
            paste = store.get(paste_id)
            if paste:
                self._send_text(paste["content"])
            else:
                self._send_json({"error": "Not found"}, 404)
        elif path.path.startswith("/"):
            paste_id = path.path[1:]
            paste = store.get(paste_id)
            if paste:
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
        )
        
        if "error" in result:
            self._send_json(result, 400)
        else:
            self._send_json(result, 201)
    
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
<button type="submit">🚀 Create Paste</button>
</form>
<div id="r" class="recent"></div>
<script>
document.getElementById('f').onsubmit=async(e)=>{
e.preventDefault();
const d={content:document.getElementById('c').value,title:document.getElementById('t').value,syntax:document.getElementById('s').value,expiry_hours:document.getElementById('e').value};
const res=await fetch('/api/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
const j=await res.json();if(j.id)location.href='/'+j.id;else alert(j.error||'Error');
};
fetch('/api/list').then(r=>r.json()).then(d=>{
const el=document.getElementById('r');
if(d.pastes&&d.pastes.length){el.innerHTML='<h3>Recent</h3>'+d.pastes.map(p=>'<div><a href="/'+p.id+'">'+p.title+'</a> <small>('+p.syntax+', '+p.size+'B)</small></div>').join('')}
});
</script></body></html>"""
    
    def _render_paste(self, paste):
        import html as html_module
        escaped = html_module.escape(paste["content"])
        return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html_module.escape(paste['title'])} - PasteHut</title>
<style>
body{{font-family:monospace;background:#1a1a2e;color:#eee;max-width:800px;margin:40px auto;padding:20px}}
h1{{color:#e94560}}.meta{{color:#666;font-size:12px;margin-bottom:20px}}
pre{{background:#16213e;padding:16px;border-radius:4px;overflow-x:auto;white-space:pre-wrap;word-break:break-all}}
a{{color:#e94560}}.actions{{margin-top:16px}}
button{{background:#16213e;color:#eee;border:1px solid #333;padding:8px 16px;border-radius:4px;cursor:pointer}}
</style></head><body>
<h1>{html_module.escape(paste['title'])}</h1>
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
    
    def _render_404(self):
        return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>404 - PasteHut</title>
<style>body{font-family:monospace;background:#1a1a2e;color:#eee;text-align:center;padding:100px}h1{color:#e94560;font-size:48px}a{color:#e94560}</style></head>
<body><h1>404</h1><p>This paste doesn't exist or has expired.</p><a href="/">← Go home</a></body></html>"""
    
    def log_message(self, format, *args):
        print(f"[PasteHut] {args[0]}")


# ============ 入口 ============

def main():
    parser = argparse.ArgumentParser(description="PasteHut - Minimal Pastebin")
    parser.add_argument("--port", type=int, default=9292)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--data-dir", default=DATA_DIR)
    args = parser.parse_args()
    
    global store
    store = PasteStore(args.data_dir)
    
    server = HTTPServer((args.host, args.port), PasteHandler)
    print(f"📋 PasteHut running on http://{args.host}:{args.port}")
    print(f"   Data dir: {args.data_dir}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 PasteHut stopped")
        server.server_close()


if __name__ == "__main__":
    main()
