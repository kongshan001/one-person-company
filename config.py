#!/usr/bin/env python3
"""
OnePersonCo 全局配置模块

集中管理各产品与基础设施的配置常量，避免散落在各文件中的硬编码值。
各模块通过 from config import ... 引用。

支持通过环境变量覆盖部分配置：
  PINGBOT_API_KEY        — PingBot API 鉴权密钥
  PINGBOT_ALERT_WEBHOOK  — PingBot 告警 Webhook URL

用法:
  from config import PasteHutConfig, PingBotConfig, IconForgeConfig, InfraConfig
"""

import os
from typing import FrozenSet, List, Dict


class PasteHutConfig:
    """PasteHut 代码粘贴服务配置

    Attributes:
        DATA_DIR: 数据存储目录
        MAX_PASTE_SIZE: 单条粘贴最大字节数 (512KB)
        DEFAULT_EXPIRY_HOURS: 默认过期小时数 (7天)
        MAX_EXPIRY_HOURS: 最大过期小时数 (30天)
        RATE_LIMIT_WINDOW: 速率限制时间窗口（秒）
        RATE_LIMIT_MAX: 时间窗口内最大请求数
        DEFAULT_PORT: 默认 HTTP 端口
        DEFAULT_HOST: 默认监听地址
        VIEWS_FLUSH_INTERVAL: 视图计数批量写入阈值
        VIEWS_FLUSH_SECONDS: 视图计数定时写入间隔（秒）
        ALLOWED_SYNTAXES: 允许的语法高亮类型集合
    """
    DATA_DIR: str = os.path.expanduser("~/.pastehut/data")
    MAX_PASTE_SIZE: int = 512 * 1024  # 512KB
    DEFAULT_EXPIRY_HOURS: int = 24 * 7  # 7天
    MAX_EXPIRY_HOURS: int = 24 * 30  # 30天
    RATE_LIMIT_WINDOW: int = 60  # 秒
    RATE_LIMIT_MAX: int = 10  # 每分钟最多10条
    DEFAULT_PORT: int = 9292
    DEFAULT_HOST: str = "0.0.0.0"

    # Views flush 配置
    VIEWS_FLUSH_INTERVAL: int = 10  # 每 10 次视图递增 flush 一次
    VIEWS_FLUSH_SECONDS: int = 30   # 或每 30 秒 flush 一次

    ALLOWED_SYNTAXES: FrozenSet[str] = frozenset({
        "text", "python", "javascript", "html", "css", "json", "sql", "bash"
    })


class PingBotConfig:
    """PingBot 可用性监控服务配置

    Attributes:
        DB_PATH: SQLite 数据库文件路径
        CHECK_INTERVAL: 检查间隔（秒）
        REQUEST_TIMEOUT: HTTP 请求超时（秒）
        MAX_HISTORY_DAYS: 历史记录保留天数
        MAX_BODY_READ: HTTP 响应体最大读取字节数 (64KB)
        DEFAULT_PORT: 默认 HTTP 端口
        DEFAULT_HOST: 默认监听地址
        API_KEY: API 鉴权密钥（环境变量 PINGBOT_API_KEY）
        ALERT_WEBHOOK_URL: 告警 Webhook URL（环境变量 PINGBOT_ALERT_WEBHOOK）
    """
    DB_PATH: str = os.path.expanduser("~/.pingbot/pingbot.db")
    CHECK_INTERVAL: int = 60  # 秒
    REQUEST_TIMEOUT: int = 10  # 秒
    MAX_HISTORY_DAYS: int = 30
    MAX_BODY_READ: int = 65536  # 64KB
    DEFAULT_PORT: int = 8081
    DEFAULT_HOST: str = "0.0.0.0"

    # API 鉴权
    API_KEY: str = os.environ.get("PINGBOT_API_KEY", "")

    # 告警
    ALERT_WEBHOOK_URL: str = os.environ.get("PINGBOT_ALERT_WEBHOOK", "")


class IconForgeConfig:
    """IconForge AI 图标生成服务配置

    Attributes:
        POLLINATIONS_URL: Pollinations API 模板 URL
        DEFAULT_SIZE: 默认图标尺寸 (px)
        MIN_FILE_SIZE: 最小有效文件大小（字节），低于此视为生成失败
        DELAY_BETWEEN_REQUESTS: 请求间隔（秒），防止速率限制
        MAX_RETRIES: 最大重试次数
        SIZES: 支持的图标尺寸列表
        STYLE_KEYWORDS: 风格关键词映射
        TYPE_KEYWORDS: 类型关键词映射
    """
    POLLINATIONS_URL: str = (
        "https://image.pollinations.ai/prompt/{prompt}"
        "?width={w}&height={h}&seed={seed}&nologo=true"
    )
    DEFAULT_SIZE: int = 512
    MIN_FILE_SIZE: int = 5000  # 5KB
    DELAY_BETWEEN_REQUESTS: int = 3  # 秒
    MAX_RETRIES: int = 2
    SIZES: List[int] = [64, 128, 256, 512]

    STYLE_KEYWORDS: Dict[str, str] = {
        "pixel": "pixel art, retro, clean edges, game boy style, 16-bit",
        "cartoon": "cartoon, cute, bold outlines, flat shading, bright colors, chibi",
        "realistic": "3D rendered, realistic, detailed texture, dramatic lighting, PBR",
        "dark": "dark fantasy, gothic, weathered, ominous glow, desaturated, bloodborne style",
        "anime": "anime RPG, cel shading, pastel, kawaii, clean vector, gacha style",
        "chinese": "Chinese ink painting, watercolor, traditional, elegant, xianxia",
        "sci-fi": "sci-fi, cyberpunk, neon glow, holographic, futuristic, clean design",
    }

    TYPE_KEYWORDS: Dict[str, str] = {
        "icon": "game item icon, isolated on solid background, centered composition",
        "sprite": "character sprite sheet, multiple poses, transparent background",
        "background": "game background, panoramic, parallax ready, seamless",
        "tileset": "tileset, seamless tiles, 16x16 grid, game map element",
        "ui": "game UI element, button, panel, frame, clean design",
    }


class InfraConfig:
    """基础设施配置

    Attributes:
        BACKUP_DIR: 备份文件存储目录
        RETENTION_DAYS: 备份保留天数
        LOG_DIR: 日志文件目录
        LOG_RETENTION_DAYS: 日志保留天数
        REPORT_DIR: 月度报告输出目录
        PID_DIR: 进程 PID 文件目录
        HEALTH_CHECK_TIMEOUT: 健康检查超时（秒）
        HEALTH_CHECK_INTERVAL: 健康检查重试间隔（秒）
    """
    # 备份
    BACKUP_DIR: str = os.path.expanduser("~/.onepersonco/backups")
    RETENTION_DAYS: int = 30

    # 日志
    LOG_DIR: str = os.path.expanduser("~/.onepersonco/logs/")
    LOG_RETENTION_DAYS: int = 7

    # 报告
    REPORT_DIR: str = os.path.expanduser("~/.onepersonco/reports")

    # 部署
    PID_DIR: str = os.path.expanduser("/tmp/onepersonco-pids")
    HEALTH_CHECK_TIMEOUT: int = 30
    HEALTH_CHECK_INTERVAL: int = 2


# 项目根目录（从本文件位置推算）
PROJECT_ROOT: str = os.path.dirname(os.path.abspath(__file__))
