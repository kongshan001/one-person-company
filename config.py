#!/usr/bin/env python3
"""
OnePersonCo 全局配置模块

集中管理各产品与基础设施的配置常量，避免散落在各文件中的硬编码值。
各模块通过 from config import ... 引用。

用法:
  from config import PasteHutConfig, PingBotConfig, InfraConfig
"""

import os


class PasteHutConfig:
    """PasteHut 配置"""
    DATA_DIR = os.path.expanduser("~/.pastehut/data")
    MAX_PASTE_SIZE = 512 * 1024  # 512KB
    DEFAULT_EXPIRY_HOURS = 24 * 7  # 7天
    MAX_EXPIRY_HOURS = 24 * 30  # 30天
    RATE_LIMIT_WINDOW = 60  # 秒
    RATE_LIMIT_MAX = 10  # 每分钟最多10条
    DEFAULT_PORT = 9292
    DEFAULT_HOST = "0.0.0.0"

    # Views flush 配置
    VIEWS_FLUSH_INTERVAL = 10  # 每 10 次视图递增 flush 一次
    VIEWS_FLUSH_SECONDS = 30   # 或每 30 秒 flush 一次

    ALLOWED_SYNTAXES = frozenset({
        "text", "python", "javascript", "html", "css", "json", "sql", "bash"
    })


class PingBotConfig:
    """PingBot 配置"""
    DB_PATH = os.path.expanduser("~/.pingbot/pingbot.db")
    CHECK_INTERVAL = 60  # 秒
    REQUEST_TIMEOUT = 10  # 秒
    MAX_HISTORY_DAYS = 30
    MAX_BODY_READ = 65536  # 64KB
    DEFAULT_PORT = 8081
    DEFAULT_HOST = "0.0.0.0"

    # API 鉴权
    API_KEY = os.environ.get("PINGBOT_API_KEY", "")

    # 告警
    ALERT_WEBHOOK_URL = os.environ.get("PINGBOT_ALERT_WEBHOOK", "")


class IconForgeConfig:
    """IconForge 配置"""
    POLLINATIONS_URL = (
        "https://image.pollinations.ai/prompt/{prompt}"
        "?width={w}&height={h}&seed={seed}&nologo=true"
    )
    DEFAULT_SIZE = 512
    MIN_FILE_SIZE = 5000  # 5KB
    DELAY_BETWEEN_REQUESTS = 3  # 秒
    MAX_RETRIES = 2
    SIZES = [64, 128, 256, 512]

    STYLE_KEYWORDS = {
        "pixel": "pixel art, retro, clean edges, game boy style, 16-bit",
        "cartoon": "cartoon, cute, bold outlines, flat shading, bright colors, chibi",
        "realistic": "3D rendered, realistic, detailed texture, dramatic lighting, PBR",
        "dark": "dark fantasy, gothic, weathered, ominous glow, desaturated, bloodborne style",
        "anime": "anime RPG, cel shading, pastel, kawaii, clean vector, gacha style",
        "chinese": "Chinese ink painting, watercolor, traditional, elegant, xianxia",
        "sci-fi": "sci-fi, cyberpunk, neon glow, holographic, futuristic, clean design",
    }

    TYPE_KEYWORDS = {
        "icon": "game item icon, isolated on solid background, centered composition",
        "sprite": "character sprite sheet, multiple poses, transparent background",
        "background": "game background, panoramic, parallax ready, seamless",
        "tileset": "tileset, seamless tiles, 16x16 grid, game map element",
        "ui": "game UI element, button, panel, frame, clean design",
    }


class InfraConfig:
    """基础设施配置"""
    # 备份
    BACKUP_DIR = os.path.expanduser("~/.onepersonco/backups")
    RETENTION_DAYS = 30

    # 日志
    LOG_DIR = os.path.expanduser("~/.onepersonco/logs/")
    LOG_RETENTION_DAYS = 7

    # 报告
    REPORT_DIR = os.path.expanduser("~/.onepersonco/reports")

    # 部署
    PID_DIR = os.path.expanduser("/tmp/onepersonco-pids")
    HEALTH_CHECK_TIMEOUT = 30
    HEALTH_CHECK_INTERVAL = 2


# 项目根目录（从本文件位置推算）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
