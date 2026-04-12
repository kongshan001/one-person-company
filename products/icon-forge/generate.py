#!/usr/bin/env python3
"""
IconForge - AI 游戏图标生成器
核心生成脚本：批量文生图 + 质检 + 多尺寸 + 打包

用法:
  python generate.py --prompt "dark fantasy sword" --style dark --count 10
  python generate.py --batch prompts.txt --style pixel --output ./output
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.parse
import zipfile
from datetime import datetime
from pathlib import Path

# ============ 配置 ============

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}?width={w}&height={h}&seed={seed}&nologo=true"

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

SIZES = [64, 128, 256, 512]
DEFAULT_SIZE = 512
MIN_FILE_SIZE = 5000  # 5KB, 小于此值视为损坏
DELAY_BETWEEN_REQUESTS = 3  # 秒, 避免限流
MAX_RETRIES = 2


# ============ 核心函数 ============

def build_prompt(user_prompt: str, style: str = None, asset_type: str = "icon") -> str:
    """构建完整的文生图 prompt"""
    parts = []
    if style and style in STYLE_KEYWORDS:
        parts.append(STYLE_KEYWORDS[style])
    parts.append(user_prompt)
    if asset_type in TYPE_KEYWORDS:
        parts.append(TYPE_KEYWORDS[asset_type])
    return ", ".join(parts)


def generate_image(prompt: str, seed: int = None, size: int = DEFAULT_SIZE,
                   output_path: str = None) -> str:
    """调用 Pollinations.ai 生成单张图片"""
    if seed is None:
        seed = int(time.time() * 1000) % 2**31
    
    encoded_prompt = urllib.parse.quote(prompt)
    url = POLLINATIONS_URL.format(prompt=encoded_prompt, w=size, h=size, seed=seed)
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
            
            if len(data) < MIN_FILE_SIZE:
                print(f"  ⚠️ 生成的图片太小 ({len(data)} bytes), 可能失败, 重试...")
                time.sleep(DELAY_BETWEEN_REQUESTS)
                continue
            
            if output_path:
                # Pollinations 返回 JPEG, 先保存原始
                raw_path = output_path + ".raw"
                with open(raw_path, "wb") as f:
                    f.write(data)
                
                # 转换为真正的 PNG
                try:
                    subprocess.run(
                        ["convert", raw_path, output_path],
                        check=True, capture_output=True, timeout=30
                    )
                    os.remove(raw_path)
                except (subprocess.CalledProcessError, FileNotFoundError):
                    # ImageMagick 不可用, 直接保存
                    os.rename(raw_path, output_path)
                
                return output_path
            
            return data  # 返回原始 bytes
            
        except Exception as e:
            print(f"  ⚠️ 生成失败 (尝试 {attempt+1}/{MAX_RETRIES+1}): {e}")
            if attempt < MAX_RETRIES:
                time.sleep(DELAY_BETWEEN_REQUESTS)
    
    return None


def resize_image(input_path: str, target_size: int, output_path: str) -> bool:
    """使用 ImageMagick 调整图片尺寸"""
    try:
        subprocess.run(
            ["convert", input_path, "-resize", f"{target_size}x{target_size}",
             "-quality", "95", output_path],
            check=True, capture_output=True, timeout=30
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        # 无 ImageMagick, 复制原文件
        shutil.copy2(input_path, output_path)
        return False


def quality_check(file_path: str) -> dict:
    """质检单张图片"""
    result = {"file": file_path, "passed": True, "issues": []}
    
    size = os.path.getsize(file_path)
    if size < MIN_FILE_SIZE:
        result["passed"] = False
        result["issues"].append(f"文件太小: {size} bytes")
    
    # 可以加更多检查: 分辨率, 感知哈希去重等
    return result


def create_preview(output_dir: str, manifest: list, project_name: str):
    """创建 HTML 预览页"""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{project_name} - Asset Preview</title>
<style>
  body {{ font-family: system-ui; background: #1a1a2e; color: #eee; padding: 20px; }}
  h1 {{ color: #e94560; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }}
  .card {{ background: #16213e; border-radius: 8px; padding: 12px; text-align: center; }}
  .card img {{ max-width: 100%; border-radius: 4px; image-rendering: pixelated; }}
  .card .name {{ font-size: 12px; color: #aaa; margin-top: 8px; word-break: break-all; }}
</style>
</head>
<body>
<h1>🎨 {project_name} - Generated Assets</h1>
<div class="grid">
"""
    for item in manifest:
        for size in SIZES:
            size_dir = f"size_{size}"
            rel_path = f"{size_dir}/{item['filename']}"
            html += f"""<div class="card">
  <img src="{rel_path}" alt="{item.get('prompt', item['filename'])}">
  <div class="name">{item['filename']} ({size}px)</div>
</div>\n"""

    html += """</div>
</body>
</html>"""
    
    preview_path = os.path.join(output_dir, "index.html")
    with open(preview_path, "w") as f:
        f.write(html)
    return preview_path


def create_zip(output_dir: str, project_name: str) -> str:
    """打包为 ZIP"""
    zip_path = os.path.join(output_dir, f"{project_name}_assets.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(output_dir):
            for file in files:
                if file.endswith(".zip"):
                    continue
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, output_dir)
                zf.write(file_path, arcname)
    return zip_path


# ============ 主流程 ============

def run_batch(prompts: list, style: str, asset_type: str, output_dir: str,
              project_name: str, count: int = 1) -> dict:
    """批量生成主流程"""
    os.makedirs(output_dir, exist_ok=True)
    
    manifest = []
    stats = {"total": 0, "success": 0, "failed": 0, "quality_issues": 0}
    
    for i, prompt_text in enumerate(prompts):
        full_prompt = build_prompt(prompt_text, style, asset_type)
        print(f"\n🎨 [{i+1}/{len(prompts)}] 生成: {prompt_text}")
        print(f"   Prompt: {full_prompt}")
        
        for j in range(count):
            stats["total"] += 1
            seed = int(time.time() * 1000 + i * 1000 + j) % 2**31
            filename = f"{style or 'default'}_{prompt_text[:30].replace(' ', '_')}_{seed % 10000}.png"
            
            # 生成原始 512x512
            raw_dir = os.path.join(output_dir, f"size_{DEFAULT_SIZE}")
            os.makedirs(raw_dir, exist_ok=True)
            raw_path = os.path.join(raw_dir, filename)
            
            result = generate_image(full_prompt, seed=seed, output_path=raw_path)
            
            if result is None:
                print(f"  ❌ 生成失败")
                stats["failed"] += 1
                continue
            
            # 质检
            qc = quality_check(raw_path)
            if not qc["passed"]:
                print(f"  ⚠️ 质检失败: {qc['issues']}")
                stats["quality_issues"] += 1
                # 不删除, 保留供人工审核
            
            # 生成多尺寸
            for size in SIZES:
                if size == DEFAULT_SIZE:
                    continue
                size_dir = os.path.join(output_dir, f"size_{size}")
                os.makedirs(size_dir, exist_ok=True)
                size_path = os.path.join(size_dir, filename)
                resize_image(raw_path, size, size_path)
            
            manifest.append({
                "filename": filename,
                "prompt": full_prompt,
                "seed": seed,
                "style": style,
                "original_prompt": prompt_text,
                "quality_passed": qc["passed"],
            })
            
            stats["success"] += 1
            print(f"  ✅ 成功 → {filename}")
            
            # 限流延迟
            time.sleep(DELAY_BETWEEN_REQUESTS)
    
    # 保存 manifest
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    # 创建预览页
    if manifest:
        create_preview(output_dir, manifest, project_name)
    
    # 打包
    zip_path = create_zip(output_dir, project_name)
    
    stats["manifest"] = manifest_path
    stats["zip"] = zip_path
    
    return stats


# ============ CLI ============

def main():
    parser = argparse.ArgumentParser(description="IconForge - AI Game Icon Generator")
    parser.add_argument("--prompt", "-p", help="单个 prompt")
    parser.add_argument("--batch", "-b", help="批量 prompt 文件 (每行一个)")
    parser.add_argument("--style", "-s", choices=list(STYLE_KEYWORDS.keys()), help="风格")
    parser.add_argument("--type", "-t", choices=list(TYPE_KEYWORDS.keys()), default="icon", help="资产类型")
    parser.add_argument("--count", "-n", type=int, default=1, help="每个 prompt 生成数量")
    parser.add_argument("--output", "-o", default="./output", help="输出目录")
    parser.add_argument("--name", help="项目名称 (用于ZIP和预览页)")
    
    args = parser.parse_args()
    
    if not args.prompt and not args.batch:
        parser.error("请提供 --prompt 或 --batch")
    
    # 收集 prompts
    prompts = []
    if args.prompt:
        prompts.append(args.prompt)
    if args.batch:
        with open(args.batch) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    prompts.append(line)
    
    project_name = args.name or f"iconforge_{datetime.now().strftime('%Y%m%d_%H%M')}"
    
    print(f"🚀 IconForge 启动")
    print(f"   Prompts: {len(prompts)}")
    print(f"   每个生成: {args.count} 张")
    print(f"   风格: {args.style or 'default'}")
    print(f"   类型: {args.type}")
    print(f"   输出: {args.output}")
    
    stats = run_batch(
        prompts=prompts,
        style=args.style,
        asset_type=args.type,
        output_dir=args.output,
        project_name=project_name,
        count=args.count,
    )
    
    print(f"\n{'='*50}")
    print(f"🎉 生成完成!")
    print(f"   总计: {stats['total']}")
    print(f"   成功: {stats['success']}")
    print(f"   失败: {stats['failed']}")
    print(f"   质检问题: {stats['quality_issues']}")
    print(f"   清单: {stats['manifest']}")
    print(f"   打包: {stats['zip']}")


if __name__ == "__main__":
    main()
