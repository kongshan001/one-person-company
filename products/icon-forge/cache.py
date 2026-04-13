#!/usr/bin/env python3
"""
IconForge 缓存管理器

避免相同 prompt 重复生成，节省 API 调用和时间

缓存策略：
- 以 prompt+style+seed 的 SHA256 为 key
- 存储生成结果路径和元数据
- 支持 TTL 过期清理
- 支持缓存命中率统计
"""

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Dict, Optional, Any


class IconCache:
    """IconForge 生成缓存"""
    
    def __init__(self, cache_dir: Optional[str] = None) -> None:
        self.cache_dir: str = cache_dir or os.path.expanduser("~/.iconforge/cache")
        self.index_path: str = os.path.join(self.cache_dir, "index.json")
        self._index: Dict[str, Dict[str, Any]] = {}
        self._hits: int = 0
        self._misses: int = 0
        os.makedirs(self.cache_dir, exist_ok=True)
        self._load_index()
    
    def _cache_key(self, prompt: str, style: Optional[str] = None,
                   seed: Optional[int] = None, size: int = 512) -> str:
        """生成缓存 key"""
        raw = f"{prompt}|{style}|{seed}|{size}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
    
    def _load_index(self) -> None:
        """加载缓存索引"""
        if os.path.exists(self.index_path):
            try:
                with open(self.index_path) as f:
                    self._index = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._index = {}
    
    def _save_index(self) -> None:
        """保存缓存索引"""
        with open(self.index_path, "w") as f:
            json.dump(self._index, f, indent=2)
    
    def get(self, prompt: str, style: Optional[str] = None,
            seed: Optional[int] = None, size: int = 512) -> Optional[str]:
        """
        查找缓存
        
        返回: 缓存文件路径 or None
        """
        key = self._cache_key(prompt, style, seed, size)
        
        if key in self._index:
            entry = self._index[key]
            # 检查文件是否还存在
            cache_file = os.path.join(self.cache_dir, key + ".png")
            if os.path.exists(cache_file):
                # 检查 TTL
                if entry.get("ttl", 0) > 0:
                    age = time.time() - entry.get("created", 0)
                    if age > entry["ttl"]:
                        self._evict(key)
                        self._misses += 1
                        return None
                
                self._hits += 1
                return cache_file
        
        self._misses += 1
        return None
    
    def put(self, prompt: str, style: Optional[str] = None,
            seed: Optional[int] = None, size: int = 512,
            source_path: Optional[str] = None, data: Optional[bytes] = None,
            ttl: int = 0) -> Optional[str]:
        """
        存入缓存
        
        Args:
            source_path: 源文件路径（复制到缓存）
            data: 或直接提供二进制数据
            ttl: 生存秒数 (0=永不过期)
        
        返回: 缓存文件路径
        """
        key = self._cache_key(prompt, style, seed, size)
        cache_file = os.path.join(self.cache_dir, key + ".png")
        
        if data is not None:
            with open(cache_file, "wb") as f:
                f.write(data)
        elif source_path and os.path.exists(source_path):
            import shutil
            shutil.copy2(source_path, cache_file)
        else:
            return None
        
        self._index[key] = {
            "prompt": prompt[:100],
            "style": style,
            "seed": seed,
            "size": size,
            "created": time.time(),
            "ttl": ttl,
            "source": source_path,
        }
        self._save_index()
        return cache_file
    
    def _evict(self, key: str) -> None:
        """清除单个缓存"""
        if key in self._index:
            cache_file = os.path.join(self.cache_dir, key + ".png")
            if os.path.exists(cache_file):
                os.remove(cache_file)
            del self._index[key]
            self._save_index()
    
    def cleanup(self, max_age_days: int = 30) -> int:
        """清理过期缓存
        
        Args:
            max_age_days: 最大保留天数
        
        Returns:
            被清理的缓存条目数
        """
        now = time.time()
        cutoff = now - (max_age_days * 86400)
        evicted = 0
        
        for key in list(self._index.keys()):
            entry = self._index[key]
            created = entry.get("created", 0)
            ttl = entry.get("ttl", 0)
            
            if created < cutoff:
                self._evict(key)
                evicted += 1
            elif ttl > 0 and (now - created) > ttl:
                self._evict(key)
                evicted += 1
        
        return evicted
    
    def stats(self) -> Dict[str, Any]:
        """缓存统计"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total else 0
        cache_size = 0
        file_count = 0
        for f in Path(self.cache_dir).glob("*.png"):
            cache_size += f.stat().st_size
            file_count += 1
        
        return {
            "entries": len(self._index),
            "files": file_count,
            "size_mb": round(cache_size / (1024 * 1024), 2),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate_pct": round(hit_rate, 1),
        }
