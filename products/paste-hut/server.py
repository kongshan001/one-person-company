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
import logging
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
from utils import send_cors_headers, handle_options, send_json, send_html, send_text, sanitize_id, truncate_text, format_bytes, get_logger

log = get_logger("PasteHut")


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

# 过期清理配置
CLEANUP_INTERVAL_SECONDS = int(os.environ.get("PASTEHUT_CLEANUP_INTERVAL", "600"))  # 默认10分钟


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
        # 过期索引：{paste_id: expires_at_iso}，用于增量清理
        self._expiry_index = {}
        self._rebuild_expiry_index()
        # 内容哈希索引：{sha256_hex[:16]: paste_id}，用于检测重复内容
        self._content_hash_index = {}
        self._rebuild_content_hash_index()

    def get_stats(self) -> dict:
        """获取 PasteHut 的聚合统计数据

        Returns:
            包含总量、视图、语法分布等统计信息的字典
        """
        total_pastes = len(self.meta)
        total_views = sum(m.get("views", 0) for m in self.meta.values())
        total_size = sum(m.get("size", 0) for m in self.meta.values())
        # 语法分布
        syntax_counts = {}
        for m in self.meta.values():
            s = m.get("syntax", "text")
            syntax_counts[s] = syntax_counts.get(s, 0) + 1
        # 阅后即焚数量
        burn_count = sum(1 for m in self.meta.values() if m.get("burn_after_read"))
        # 密码保护数量
        password_count = sum(1 for m in self.meta.values() if m.get("has_password"))

        return {
            "total_pastes": total_pastes,
            "total_views": total_views,
            "total_size_bytes": total_size,
            "total_size_kb": round(total_size / 1024, 1),
            "syntax_distribution": syntax_counts,
            "burn_after_read_count": burn_count,
            "password_protected_count": password_count,
        }
    
    def _load_meta(self) -> dict:
        if self.meta_file.exists():
            try:
                return json.loads(self.meta_file.read_text())
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    def _rebuild_expiry_index(self):
        """从 meta 构建过期索引，用于增量清理而非全量扫描
        
        索引包含所有有 expires_at 字段的 paste（包括已过期的），
        以便 cleanup_expired 能正确识别并清理它们。
        """
        self._expiry_index.clear()
        for paste_id, info in self.meta.items():
            expires = info.get("expires_at")
            if not expires:
                continue
            try:
                # 验证日期格式是否可解析
                expires_dt = datetime.fromisoformat(expires)
                if expires_dt.tzinfo is None:
                    expires_dt = expires_dt.replace(tzinfo=timezone.utc)
                self._expiry_index[paste_id] = expires
            except (ValueError, TypeError):
                # 无法解析的过期时间，跳过
                pass

    def _update_expiry_index(self, paste_id: str, info: dict):
        """创建/更新单个 paste 的过期索引条目"""
        expires = info.get("expires_at")
        if expires:
            self._expiry_index[paste_id] = expires
        else:
            self._expiry_index.pop(paste_id, None)

    def _rebuild_content_hash_index(self):
        """从磁盘文件重建内容哈希索引，用于快速检测重复内容"""
        self._content_hash_index.clear()
        for paste_id in self.meta:
            paste_file = self.data_dir / f"{paste_id}.txt"
            if paste_file.exists():
                try:
                    content = paste_file.read_text()
                    content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                    # 保留最新的 paste_id（如果多个 paste 内容相同）
                    self._content_hash_index[content_hash] = paste_id
                except IOError:
                    pass

    def check_duplicate(self, content: str) -> dict:
        """检查内容是否已存在

        Args:
            content: 要检查的文本内容

        Returns:
            包含 is_duplicate 和 existing_id 的字典；如不重复则 existing_id 为 None
        """
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        existing_id = self._content_hash_index.get(content_hash)
        if existing_id and existing_id in self.meta:
            return {"is_duplicate": True, "existing_id": existing_id}
        return {"is_duplicate": False, "existing_id": None}

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
    def _hash_password(password: str, salt: str = "") -> str:
        """Hash password with per-paste random salt for secure storage

        使用每个粘贴独立的随机盐值，防止彩虹表攻击。
        如果未提供盐值，自动生成随机盐（新建粘贴时）。

        Args:
            password: 原始密码
            salt: 盐值，为空时自动生成

        Returns:
            "salt$hash" 格式的字符串
        """
        if not salt:
            salt = os.urandom(16).hex()
        h = hashlib.sha256((salt + password).encode()).hexdigest()
        return f"{salt}${h}"
    
    def create(self, content: str, title: str = "", syntax: str = "text",
               expiry_hours: int = None, ip: str = "unknown",
               burn_after_read: bool = False, password: str = "",
               tags: list = None) -> dict:
        """创建 paste
        
        Args:
            content: 粘贴内容
            title: 标题（可选）
            syntax: 语法高亮类型
            expiry_hours: 过期时间（小时）
            ip: 创建者 IP
            burn_after_read: 阅后即焚，首次查看后自动删除
            password: 访问密码（可选，空字符串表示无密码）
            tags: 标签列表（可选，最多5个，每个最长32字符）
        
        Returns:
            创建结果字典，含 id、delete_key 等；失败时含 error
        """
        if len(content) > MAX_PASTE_SIZE:
            return {"error": f"内容超过限制 ({MAX_PASTE_SIZE // 1024}KB)"}
        
        # 校验 title 长度
        if title and len(title) > 200:
            return {"error": "标题长度不能超过200字符"}
        
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
        
        # 处理标签：清洗、去重、限制数量
        clean_tags = []
        if tags and isinstance(tags, list):
            seen = set()
            for tag in tags:
                if not isinstance(tag, str):
                    continue
                tag = tag.strip().lower()
                if not tag or len(tag) > 32:
                    continue
                # 只允许字母数字、连字符、下划线、中文
                if re.fullmatch(r'[\w\u4e00-\u9fff-]+', tag) and tag not in seen:
                    clean_tags.append(tag)
                    seen.add(tag)
                if len(clean_tags) >= 5:
                    break
        
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
            "tags": clean_tags,
        }
        self._save_meta()
        self._update_expiry_index(paste_id, self.meta[paste_id])
        # 更新内容哈希索引
        content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        self._content_hash_index[content_hash] = paste_id
        
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
            # 清除内容哈希索引中对应的条目
            meta = self.meta[paste_id]
            del self.meta[paste_id]
            # 反向查找并移除哈希索引（安全：即使哈希冲突也只移除当前 paste_id 的映射）
            hash_to_remove = None
            for h, pid in list(self._content_hash_index.items()):
                if pid == paste_id:
                    hash_to_remove = h
                    break
            if hash_to_remove:
                del self._content_hash_index[hash_to_remove]
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
        """基于过期索引增量清理过期 paste，避免全量扫描

        通过 _expiry_index 只检查有 expires_at 字段的 paste，
        相比遍历全部 meta 大幅减少比较次数。
        清理完成后自动更新索引。
        """
        now = datetime.now(timezone.utc)
        expired = []
        for pid, exp in list(self._expiry_index.items()):
            try:
                exp_dt = datetime.fromisoformat(exp)
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if exp_dt <= now:
                    expired.append(pid)
            except (ValueError, TypeError):
                # 无法解析的过期时间，视为已过期以触发重建
                expired.append(pid)

        for pid in expired:
            self.delete(pid)
            self._expiry_index.pop(pid, None)

        return len(expired)
    
    # 安全字段白名单，用于列表返回（不含密码哈希、delete_key等敏感字段）
    _SAFE_FIELDS = frozenset({
        "id", "title", "syntax", "size", "created_at", "expires_at",
        "views", "burn_after_read", "has_password", "tags",
    })

    def _filter_safe_fields(self, paste_meta: dict) -> dict:
        """过滤敏感字段，返回安全视图，同时包含实时 views 计数"""
        current_views = paste_meta.get("views", 0) + self._views_dirty.get(paste_meta.get("id", ""), 0)
        item = {k: v for k, v in paste_meta.items() if k in self._SAFE_FIELDS}
        item["views"] = current_views
        return item

    def list_recent(self, limit: int = 20, query: str = "",
                    offset: int = 0, sort_by: str = "created_at",
                    sort_order: str = "desc",
                    search_content: bool = False) -> dict:
        """列出最近的 paste（不含敏感字段），支持分页和排序

        Args:
            limit: 返回数量上限
            query: 搜索关键词，匹配标题和标签（不区分大小写），为空则不过滤；
                   若 search_content=True，也匹配内容文本
            offset: 分页偏移量，从0开始
            sort_by: 排序字段，可选 created_at 或 views
            sort_order: 排序方向，desc 降序 / asc 升序
            search_content: 是否搜索内容文本（较慢，默认仅搜标题和标签）

        Returns:
            包含 pastes 列表、total 总数、offset、limit 的分页字典
        """
        # 校验排序字段
        allowed_sort = {"created_at", "views"}
        if sort_by not in allowed_sort:
            sort_by = "created_at"
        # 校验排序方向
        if sort_order not in ("desc", "asc"):
            sort_order = "desc"

        pastes = list(self.meta.values())

        # 搜索过滤 — 默认搜标题+标签，可选搜内容
        if query and query.strip():
            q = query.strip().lower()
            if search_content:
                # 内容搜索：需读取文件，较慢但更全面
                def _matches(p: dict) -> bool:
                    if q in p.get("title", "").lower():
                        return True
                    # 搜索标签
                    if any(q in t.lower() for t in p.get("tags", [])):
                        return True
                    # 搜索内容
                    paste_file = self.data_dir / f"{p.get('id', '')}.txt"
                    if paste_file.exists():
                        try:
                            content = paste_file.read_text()
                            if q in content.lower():
                                return True
                        except IOError:
                            pass
                    return False
                pastes = [p for p in pastes if _matches(p)]
            else:
                # 快速搜索：仅标题+标签
                pastes = [p for p in pastes if q in p.get("title", "").lower()
                          or any(q in t.lower() for t in p.get("tags", []))]

        total = len(pastes)

        # 排序 — views 排序需包含脏计数
        reverse = (sort_order == "desc")
        if sort_by == "views":
            pastes.sort(key=lambda x: x.get("views", 0) + self._views_dirty.get(x.get("id", ""), 0), reverse=reverse)
        else:
            pastes.sort(key=lambda x: x.get(sort_by, ""), reverse=reverse)

        # 分页
        page_pastes = pastes[offset:offset + limit]

        # 过滤敏感字段（使用统一方法）
        result = [self._filter_safe_fields(p) for p in page_pastes]

        return {
            "pastes": result,
            "total": total,
            "offset": offset,
            "limit": limit,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
    
    def list_by_tag(self, tag: str, limit: int = 20, offset: int = 0) -> dict:
        """按标签检索 paste 列表

        Args:
            tag: 标签名（大小写不敏感）
            limit: 返回数量上限
            offset: 分页偏移量

        Returns:
            包含匹配 pastes、tag 名称、total 的字典
        """
        tag_lower = tag.strip().lower()
        if not tag_lower:
            return {"tag": tag, "pastes": [], "total": 0}

        matching = []
        for p in self.meta.values():
            paste_tags = [t.lower() for t in p.get("tags", [])]
            if tag_lower in paste_tags:
                matching.append(self._filter_safe_fields(p))

        matching.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        total = len(matching)
        page = matching[offset:offset + limit]

        return {
            "tag": tag_lower,
            "pastes": page,
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def get_all_tags(self) -> dict:
        """获取所有标签及其对应的 paste 数量

        Returns:
            包含 tags 列表（每项含 name 和 count）的字典
        """
        tag_counts: dict = {}
        for p in self.meta.values():
            for tag in p.get("tags", []):
                tag_lower = tag.lower()
                tag_counts[tag_lower] = tag_counts.get(tag_lower, 0) + 1
        tags_list = [
            {"name": name, "count": count}
            for name, count in sorted(tag_counts.items(), key=lambda x: -x[1])
        ]
        return {"tags": tags_list, "unique_count": len(tags_list)}


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
        elif path.path == "/api/stats":
            self._send_json(store.get_stats())
        elif path.path == "/api/duplicate":
            # 重复检测 API：传入 content 参数检查是否已有相同内容
            content = params.get("content", [""])[0]
            if not content:
                self._send_json({"error": "content parameter required"}, 400)
            else:
                self._send_json(store.check_duplicate(content))
        elif path.path == "/api/tags":
            self._send_json(store.get_all_tags())
        elif path.path.startswith("/api/tags/"):
            tag = path.path[len("/api/tags/"):]
            try:
                limit = int(params.get("limit", ["20"])[0])
                limit = max(1, min(limit, 100))
            except (ValueError, IndexError):
                limit = 20
            try:
                offset = int(params.get("offset", ["0"])[0])
                offset = max(0, offset)
            except (ValueError, IndexError):
                offset = 0
            self._send_json(store.list_by_tag(tag, limit=limit, offset=offset))
        elif path.path == "/api/list":
            query = params.get("q", [""])[0]
            try:
                limit = int(params.get("limit", ["20"])[0])
                limit = max(1, min(limit, 100))  # 限制1-100
            except (ValueError, IndexError):
                limit = 20
            try:
                offset = int(params.get("offset", ["0"])[0])
                offset = max(0, offset)
            except (ValueError, IndexError):
                offset = 0
            sort_by = params.get("sort", ["created_at"])[0]
            sort_order = params.get("order", ["desc"])[0]
            search_content = params.get("search_content", ["false"])[0].lower() in ("true", "1", "yes")
            result = store.list_recent(
                limit=limit, query=query, offset=offset,
                sort_by=sort_by, sort_order=sort_order,
                search_content=search_content,
            )
            self._send_json(result)
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
            tags=data.get("tags", []),
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
<input id="tg" name="tags" placeholder="Tags (comma-separated, max 5)">
<button type="submit">🚀 Create Paste</button>
</form>
<div id="r" class="recent"></div>
<script>
document.getElementById('f').onsubmit=async(e)=>{
e.preventDefault();
const d={content:document.getElementById('c').value,title:document.getElementById('t').value,syntax:document.getElementById('s').value,expiry_hours:document.getElementById('e').value,burn_after_read:document.getElementById('bar').checked,password:document.getElementById('pw').value,tags:document.getElementById('tg').value.split(',').map(t=>t.trim()).filter(t=>t)};
const res=await fetch('/api/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});
const j=await res.json();if(j.id){if(j.delete_key){console.log('Delete key:',j.delete_key);}location.href='/'+j.id;}else alert(j.error||'Error');
};
const loadList=(q)=>{const url=q?'/api/list?q='+encodeURIComponent(q):'/api/list';fetch(url).then(r=>r.json()).then(d=>{
const el=document.getElementById('r');
if(d.pastes&&d.pastes.length){el.innerHTML='<h3>Recent</h3><input id="sq" placeholder="🔍 Search..." value="'+(q||'').replace(/"/g,'&quot;')+'" style="background:#16213e;color:#eee;border:1px solid #333;padding:6px;border-radius:4px;margin-left:8px;width:200px">'+d.pastes.map(p=>'<div><a href="/'+p.id+'">'+p.title+'</a> <small>('+p.syntax+', '+p.size+'B)'+(p.tags&&p.tags.length?' '+p.tags.map(t=>'<a href="/api/tags/'+encodeURIComponent(t)+'" style="color:#0f3460;background:#16213e;padding:2px 6px;border-radius:3px;font-size:11px;text-decoration:none">#'+t+'</a>').join(' '):'')+'</small></div>').join('');document.getElementById('sq').oninput=function(){clearTimeout(window._st);window._st=setTimeout(()=>loadList(this.value),300);};}
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
        # 标签显示
        tags_html = ''
        if paste.get("tags"):
            tags_html = '<div style="margin-bottom:12px">' + ' '.join(
                f'<a href="/api/tags/{t}" style="color:#0f3460;background:#16213e;padding:3px 8px;border-radius:4px;font-size:12px;text-decoration:none">#{t}</a>'
                for t in paste["tags"]
            ) + '</div>'
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
{tags_html}
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
        """结构化请求日志：记录 method/path/status/耗时"""
        log.info("%s %s %s %s",
                 self.command,
                 self.path,
                 getattr(self, '_status_code', '-'),
                 getattr(self, '_request_duration_ms', '-'))


# ============ 过期清理线程 ============

def _cleanup_loop(store_instance: PasteStore):
    """后台线程：按配置间隔清理过期 paste（默认10分钟）"""
    while True:
        try:
            count = store_instance.cleanup_expired()
            if count:
                log.info("Cleaned up %d expired paste(s) via expiry index", count)
            # 同时 flush 残留 views
            store_instance._flush_views()
        except Exception as e:
            log.error("Cleanup error: %s", e)
        time.sleep(CLEANUP_INTERVAL_SECONDS)


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
    log.info("PasteHut running on http://%s:%d", args.host, args.port)
    log.info("Data dir: %s", args.data_dir)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        # 退出前 flush 残留 views
        store._flush_views()
        log.info("PasteHut stopped")
        server.server_close()


if __name__ == "__main__":
    main()
