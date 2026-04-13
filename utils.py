#!/usr/bin/env python3
"""
OnePersonCo 共享工具模块

提供跨产品复用的通用功能，避免代码重复。
各模块通过 from utils import ... 引用。

用法:
  from utils import send_cors_headers, format_uptime, sanitize_id
"""

import json
import re
from http.server import BaseHTTPRequestHandler
from typing import Optional


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
]


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
    handler.send_header("Access-Control-Allow-Headers", allowed_headers)
    handler.send_header("Access-Control-Max-Age", str(max_age))


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
