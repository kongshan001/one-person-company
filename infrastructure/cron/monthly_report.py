#!/usr/bin/env python3
"""
月度运营报告生成

用法:
  python monthly_report.py [--month 2026-04]
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# 引入集中配置
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from config import InfraConfig, PingBotConfig, PasteHutConfig


def generate_report(month: str, output_dir: str) -> dict:
    """生成月度报告"""
    report = {
        "month": month,
        "generated_at": datetime.utcnow().isoformat(),
        "products": {},
        "finance": {},
        "infrastructure": {},
    }
    
    # PingBot 统计（从集中配置读取路径）
    pingbot_db = PingBotConfig.DB_PATH
    if os.path.exists(pingbot_db):
        try:
            conn = sqlite3.connect(pingbot_db)
            conn.row_factory = sqlite3.Row
            # Calculate month boundaries for filtering
            month_start = f"{month}-01"
            # Next month start
            year, m = month.split("-")
            m_int = int(m)
            y_int = int(year)
            if m_int == 12:
                next_month = f"{y_int + 1}-01-01"
            else:
                next_month = f"{y_int}-{m_int + 1:02d}-01"
            total_checks = conn.execute(
                "SELECT COUNT(*) as c FROM checks WHERE checked_at >= ? AND checked_at < ?",
                (month_start, next_month)
            ).fetchone()["c"]
            up_checks = conn.execute(
                "SELECT COUNT(*) as c FROM checks WHERE is_up = 1 AND checked_at >= ? AND checked_at < ?",
                (month_start, next_month)
            ).fetchone()["c"]
            uptime = round(up_checks / total_checks * 100, 2) if total_checks else 0
            
            report["infrastructure"]["uptime"] = {
                "total_checks": total_checks,
                "up_checks": up_checks,
                "uptime_pct": uptime,
            }
            conn.close()
        except Exception as e:
            report["infrastructure"]["uptime"] = {"error": str(e)}
    
    # PasteHut 统计（从集中配置读取路径）
    pastehut_meta = str(Path(PasteHutConfig.DATA_DIR) / "meta.json")
    if os.path.exists(pastehut_meta):
        try:
            with open(pastehut_meta) as f:
                pastes = json.load(f)
            report["products"]["pastehut"] = {
                "total_pastes": len(pastes),
                "total_views": sum(p.get("views", 0) for p in pastes.values()),
                "total_size": sum(p.get("size", 0) for p in pastes.values()),
            }
        except Exception as e:
            report["products"]["pastehut"] = {"error": str(e)}
    
    # 系统信息
    report["infrastructure"]["system"] = {
        "hostname": os.uname().nodename,
        "platform": os.uname().sysname,
    }
    
    # 保存
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"report_{month}.json")
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    return report


def print_report(report: dict):
    """打印报告"""
    print(f"\n📊 Monthly Report: {report['month']}")
    print(f"   Generated: {report['generated_at']}\n")
    
    if "pastehut" in report.get("products", {}):
        ph = report["products"]["pastehut"]
        print(f"📋 PasteHut:")
        print(f"   Pastes: {ph.get('total_pastes', 'N/A')}")
        print(f"   Views: {ph.get('total_views', 'N/A')}")
        print(f"   Size: {ph.get('total_size', 0) // 1024}KB\n")
    
    if "uptime" in report.get("infrastructure", {}):
        up = report["infrastructure"]["uptime"]
        print(f"🤖 Infrastructure:")
        print(f"   Checks: {up.get('total_checks', 'N/A')}")
        print(f"   Uptime: {up.get('uptime_pct', 'N/A')}%\n")


def main():
    parser = argparse.ArgumentParser(description="Monthly Report")
    parser.add_argument("--month", default=datetime.now().strftime("%Y-%m"))
    parser.add_argument("--output", default=InfraConfig.REPORT_DIR)
    args = parser.parse_args()
    
    report = generate_report(args.month, args.output)
    print_report(report)
    print(f"✅ Report saved to {args.output}/report_{args.month}.json")


if __name__ == "__main__":
    main()
