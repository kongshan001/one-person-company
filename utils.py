#!/usr/bin/env python3
"""
OnePersonCo 共享工具模块

提供跨产品复用的通用功能，避免代码重复。
各模块通过 from utils import ... 引用。

用法:
  from utils import send_cors_headers, format_uptime, sanitize_id, get_logger
"""

import json
import logging
import os
import re
from http.server import BaseHTTPRequestHandler
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse


__all__ = [
    "send_cors_headers",
    "handle_options",
    "send_json",
    "send_html",
    "send_text",
    "parse_body",
    "sanitize_id",
    "format_uptime",
    "compute_percentiles",
    "validate_url",
    "truncate_text",
    "safe_get_path",
    "format_bytes",
    "parse_duration",
    "get_logger",
]


# ============ 统一日志 ============

_loggers: Dict[str, logging.Logger] = {}


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """获取统一的命名 Logger

    首次调用时自动配置 Formatter 和 StreamHandler，
    后续同名调用直接返回已配置的 Logger 实例。

    Args:
        name: Logger 名称，建议使用产品/模块名如 "PasteHut", "PingBot"
        level: 日志级别，默认 INFO

    Returns:
        配置好的 logging.Logger 实例
    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(f"opc.{name}")
    logger.setLevel(level)
    # 避免重复添加 handler
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        fmt = logging.Formatter(
            "[%(asctime)s] [%(name)s] %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(fmt)
        logger.addHandler(handler)
    # 不传播到 root logger，防止重复输出
    logger.propagate = False
    _loggers[name] = logger
    return logger


def send_cors_headers(
    handler: BaseHTTPRequestHandler,
    allowed_methods: str = "GET, POST, PUT, DELETE, OPTIONS",
    allowed_headers: str = "Content-Type, Authorization, X-Delete-Key",
    max_age: int = 86400,
) -> None:
    """发送 CORS 跨域响应头

    统一管理 CORS 头，避免 PasteHut / PingBot 各自维护一份。
    在 handler 的 send_response() 之后、end_headers() 之前调用。

    Args:
        handler: BaseHTTPRequestHandler 实例
        allowed_methods: 允许的 HTTP 方法
        allowed_headers: 允许的请求头
        max_age: 预检缓存时间（秒）
    """
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", allowed_methods)
    handler.send_header("Access-Control-Max-Age", str(max_age))
    handler.send_header("Access-Control-Allow-Headers", allowed_headers)


def handle_options(
    handler: BaseHTTPRequestHandler,
    allowed_methods: str = "GET, POST, PUT, DELETE, OPTIONS",
    allowed_headers: str = "Content-Type, Authorization, X-Delete-Key",
) -> None:
    """处理 CORS 预检请求 (OPTIONS)

    发送 204 No Content 并附带 CORS 头。

    Args:
        handler: BaseHTTPRequestHandler 实例
        allowed_methods: 允许的 HTTP 方法
        allowed_headers: 允许的请求头
    """
    handler.send_response(204)
    send_cors_headers(handler, allowed_methods, allowed_headers)
    handler.end_headers()


def send_json(
    handler: BaseHTTPRequestHandler,
    data: dict,
    status: int = 200,
) -> None:
    """发送 JSON 响应（含 CORS 头）

    Args:
        handler: BaseHTTPRequestHandler 实例
        data: 要序列化为 JSON 的字典
        status: HTTP 状态码
    """
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    send_cors_headers(handler)
    handler.end_headers()
    handler.wfile.write(json.dumps(data, ensure_ascii=False).encode())


def format_uptime(uptime_pct: float) -> str:
    """格式化可用率为人类可读字符串

    Args:
        uptime_pct: 可用率百分比 (0-100)

    Returns:
        格式化后的字符串，如 "99.95%" 或 "100%"
    """
    return f"{uptime_pct:.2f}%"


def sanitize_id(id_str: str, max_len: int = 64) -> Optional[str]:
    """校验并清洗 ID 字符串

    只允许小写十六进制字符，防止路径穿越攻击。

    Args:
        id_str: 待校验的 ID 字符串
        max_len: 允许的最大长度

    Returns:
        清洗后的 ID，不合法返回 None
    """
    if not id_str or len(id_str) > max_len:
        return None
    if not re.fullmatch(r'[a-f0-9]+', id_str):
        return None
    return id_str


def parse_body(handler: BaseHTTPRequestHandler) -> Optional[dict]:
    """解析请求体为 JSON 字典

    Args:
        handler: BaseHTTPRequestHandler 实例

    Returns:
        解析后的字典，解析失败返回 None
    """
    length = int(handler.headers.get("Content-Length", 0))
    if not length:
        return {}
    raw = handler.rfile.read(length).decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None


def send_html(
    handler: BaseHTTPRequestHandler,
    html: str,
    status: int = 200,
) -> None:
    """发送 HTML 响应（含 CORS 头）

    Args:
        handler: BaseHTTPRequestHandler 实例
        html: HTML 内容字符串
        status: HTTP 状态码
    """
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    send_cors_headers(handler)
    handler.end_headers()
    handler.wfile.write(html.encode())


def send_text(
    handler: BaseHTTPRequestHandler,
    text: str,
    status: int = 200,
) -> None:
    """发送纯文本响应（含 CORS 头）

    Args:
        handler: BaseHTTPRequestHandler 实例
        text: 纯文本内容
        status: HTTP 状态码
    """
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    send_cors_headers(handler)
    handler.end_headers()
    handler.wfile.write(text.encode())


def compute_percentiles(values: list, percentiles: list = None) -> dict:
    """计算百分位数值

    用于 PingBot 响应时间统计等场景。

    Args:
        values: 数值列表
        percentiles: 要计算的百分位数列表，默认 [50, 95, 99]

    Returns:
        百分位数字典，如 {"p50": 120, "p95": 340, "p99": 580}
    """
    if percentiles is None:
        percentiles = [50, 95, 99]

    if not values:
        return {f"p{p}": None for p in percentiles}

    sorted_vals = sorted(values)
    n = len(sorted_vals)
    result = {}
    for p in percentiles:
        idx = int(n * p / 100)
        idx = min(idx, n - 1)  # 防止越界
        result[f"p{p}"] = sorted_vals[idx]
    return result


def validate_url(url: str, allowed_schemes: tuple = ("http", "https")) -> Optional[str]:
    """校验 URL 格式和协议安全性

    防止 SSRF 攻击，确保 URL 格式合法且使用允许的协议。

    Args:
        url: 待校验的 URL 字符串
        allowed_schemes: 允许的协议元组，默认 ("http", "https")

    Returns:
        校验通过的 URL 字符串，不合法返回 None
    """
    if not url or not isinstance(url, str):
        return None
    try:
        parsed = urlparse(url)
    except Exception:
        return None
    if not parsed.scheme or parsed.scheme not in allowed_schemes:
        return None
    if not parsed.hostname:
        return None
    # 禁止内网地址（基本 SSRF 防护）
    hostname = parsed.hostname.lower()
    blocked = ("localhost", "127.0.0.1", "0.0.0.0", "::1",
               "169.254.169.254",  # 云元数据
               )
    if hostname in blocked:
        return None
    # 禁止私有网段的主机名（10.x, 172.16-31.x, 192.168.x）
    parts = hostname.split(".")
    if len(parts) == 4:
        try:
            octets = [int(p) for p in parts]
            if octets[0] == 10:
                return None
            if octets[0] == 172 and 16 <= octets[1] <= 31:
                return None
            if octets[0] == 192 and octets[1] == 168:
                return None
        except ValueError:
            pass
    return url


def truncate_text(text: str, max_len: int = 200, suffix: str = "...") -> str:
    """截断过长文本，附加省略后缀

    用于标题、摘要等场景的显示裁剪。

    Args:
        text: 原始文本
        max_len: 最大长度（含后缀）
        suffix: 截断后缀

    Returns:
        截断后的文本
    """
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[:max_len - len(suffix)] + suffix


def safe_get_path(base_dir: str, user_path: str) -> Optional[str]:
    """安全拼接路径，防止路径穿越

    确保拼接后的路径仍在 base_dir 下，防止 ../../ 攻击。

    Args:
        base_dir: 基础目录的绝对路径
        user_path: 用户提供的相对路径

    Returns:
        安全的绝对路径，穿越时返回 None
    """
    if not base_dir or not user_path:
        return None
    base = os.path.realpath(base_dir)
    full = os.path.realpath(os.path.join(base_dir, user_path))
    if not full.startswith(base + os.sep) and full != base:
        return None
    return full


def format_bytes(num_bytes: int) -> str:
    """将字节数格式化为人类可读字符串

    Args:
        num_bytes: 字节数

    Returns:
        格式化后的字符串，如 "1.5KB", "2.3MB"
    """
    if num_bytes < 0:
        return "0B"
    units = [("B", 1), ("KB", 1024), ("MB", 1024 ** 2),
             ("GB", 1024 ** 3), ("TB", 1024 ** 4)]
    for unit, threshold in reversed(units):
        if num_bytes >= threshold:
            value = num_bytes / threshold
            if value >= 100:
                return f"{int(value)}{unit}"
            return f"{value:.1f}{unit}"
    return "0B"


def parse_duration(duration_str: str) -> Optional[int]:
    """将人类可读的时长字符串解析为秒数

    支持格式: "30s", "5m", "2h", "7d", 以及纯数字（默认秒）。

    Args:
        duration_str: 时长字符串

    Returns:
        对应的秒数，解析失败返回 None
    """
    if not duration_str or not isinstance(duration_str, str):
        return None
    duration_str = duration_str.strip().lower()
    if not duration_str:
        return None
    # 纯数字
    if duration_str.isdigit():
        return int(duration_str)
    # 带单位
    multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
    }
    for suffix, multiplier in multipliers.items():
        if duration_str.endswith(suffix):
            num_part = duration_str[:-1]
            if num_part.isdigit():
                return int(num_part) * multiplier
    return None
