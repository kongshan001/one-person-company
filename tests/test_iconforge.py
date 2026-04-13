#!/usr/bin/env python3
"""
IconForge 模块单元测试

覆盖:
- IconCache: 缓存存取、TTL过期、统计、清理
- prompt_engine: prompt 构建、预设方案获取、预设列表
"""

import json
import os
import shutil
import sys
import tempfile
import time
import unittest

# 引入项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 引入 icon-forge 模块
_iconforge_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "products", "icon-forge"
)
sys.path.insert(0, _iconforge_dir)

import cache as icon_cache_module
import prompt_engine


class TestIconCache(unittest.TestCase):
    """IconCache 缓存模块测试"""

    def setUp(self):
        """每个测试用独立的临时缓存目录"""
        self.tmp_dir = tempfile.mkdtemp(prefix="iconforge_test_")
        self.cache = icon_cache_module.IconCache(cache_dir=self.tmp_dir)

    def tearDown(self):
        """清理临时目录"""
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)

    def test_cache_key_deterministic(self):
        """相同参数生成相同的缓存 key"""
        key1 = self.cache._cache_key("sword", style="dark", seed=42, size=512)
        key2 = self.cache._cache_key("sword", style="dark", seed=42, size=512)
        self.assertEqual(key1, key2)

    def test_cache_key_diff_prompt(self):
        """不同 prompt 生成不同的缓存 key"""
        key1 = self.cache._cache_key("sword")
        key2 = self.cache._cache_key("shield")
        self.assertNotEqual(key1, key2)

    def test_cache_key_diff_style(self):
        """不同 style 生成不同的缓存 key"""
        key1 = self.cache._cache_key("sword", style="dark")
        key2 = self.cache._cache_key("sword", style="pixel")
        self.assertNotEqual(key1, key2)

    def test_put_and_get_with_data(self):
        """通过 bytes 数据存入缓存后可取出"""
        test_data = b"\x89PNG\r\n\x1a\ntest icon data"
        result = self.cache.put("test_prompt", data=test_data)
        self.assertIsNotNone(result)
        self.assertTrue(os.path.exists(result))

        # get 应返回缓存路径
        cached = self.cache.get("test_prompt")
        self.assertIsNotNone(cached)
        self.assertTrue(os.path.exists(cached))

        # 验证内容一致
        with open(cached, "rb") as f:
            self.assertEqual(f.read(), test_data)

    def test_put_and_get_with_source_path(self):
        """通过源文件路径存入缓存后可取出"""
        # 创建临时源文件
        src = os.path.join(self.tmp_dir, "source.png")
        with open(src, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nsource data")

        result = self.cache.put("file_prompt", source_path=src)
        self.assertIsNotNone(result)

        cached = self.cache.get("file_prompt")
        self.assertIsNotNone(cached)

        with open(cached, "rb") as f:
            self.assertEqual(f.read(), b"\x89PNG\r\n\x1a\nsource data")

    def test_get_miss(self):
        """缓存未命中返回 None"""
        result = self.cache.get("nonexistent_prompt")
        self.assertIsNone(result)

    def test_get_empty_prompt(self):
        """空 prompt 的缓存查找"""
        # 空 prompt 应该也能工作（只是 key 不同）
        self.cache.put("", data=b"empty data")
        result = self.cache.get("")
        self.assertIsNotNone(result)

    def test_put_no_data_no_source(self):
        """不提供 data 和 source_path 时返回 None"""
        result = self.cache.put("test", data=None, source_path=None)
        self.assertIsNone(result)

    def test_ttl_expiry(self):
        """TTL 过期后缓存自动失效"""
        self.cache.put("ttl_test", data=b"data", ttl=1)
        # 立即获取应命中
        self.assertIsNotNone(self.cache.get("ttl_test"))

        # 等待过期
        time.sleep(1.5)
        self.assertIsNone(self.cache.get("ttl_test"))

    def test_ttl_no_expiry(self):
        """TTL=0 时永不过期"""
        self.cache.put("no_ttl_test", data=b"data", ttl=0)
        self.assertIsNotNone(self.cache.get("no_ttl_test"))

    def test_stats_initial(self):
        """初始统计全部为零"""
        stats = self.cache.stats()
        self.assertEqual(stats["entries"], 0)
        self.assertEqual(stats["files"], 0)
        self.assertEqual(stats["hits"], 0)
        self.assertEqual(stats["misses"], 0)
        self.assertEqual(stats["hit_rate_pct"], 0)

    def test_stats_after_operations(self):
        """操作后统计正确"""
        self.cache.put("s1", data=b"data1")
        self.cache.put("s2", data=b"data2")

        # 2 hits
        self.cache.get("s1")
        self.cache.get("s2")
        # 1 miss
        self.cache.get("nonexistent")

        stats = self.cache.stats()
        self.assertEqual(stats["entries"], 2)
        self.assertEqual(stats["hits"], 2)
        self.assertEqual(stats["misses"], 1)
        self.assertAlmostEqual(stats["hit_rate_pct"], 66.7, places=0)

    def test_cleanup_old_entries(self):
        """清理过期的缓存条目"""
        self.cache.put("old", data=b"old_data")

        # 手动修改创建时间模拟旧条目
        key = self.cache._cache_key("old")
        self.cache._index[key]["created"] = time.time() - 31 * 86400  # 31天前
        self.cache._save_index()

        evicted = self.cache.cleanup(max_age_days=30)
        self.assertEqual(evicted, 1)

        # 清理后 get 应该 miss
        self.assertIsNone(self.cache.get("old"))

    def test_cleanup_preserves_recent(self):
        """清理保留最近的缓存条目"""
        self.cache.put("recent", data=b"recent_data")
        evicted = self.cache.cleanup(max_age_days=30)
        self.assertEqual(evicted, 0)

        cached = self.cache.get("recent")
        self.assertIsNotNone(cached)

    def test_index_persistence(self):
        """缓存索引在重建后可恢复"""
        self.cache.put("persist", data=b"persist_data")
        self.cache.get("persist")  # 1 hit

        # 新建 IconCache 实例指向同目录
        cache2 = icon_cache_module.IconCache(cache_dir=self.tmp_dir)
        cached = cache2.get("persist")
        self.assertIsNotNone(cached)


class TestPromptEngine(unittest.TestCase):
    """prompt_engine 模块测试"""

    def test_build_pro_prompt_basic(self):
        """基本 prompt 构建"""
        result = prompt_engine.build_pro_prompt("magic sword")
        self.assertIn("prompt", result)
        self.assertIn("negative", result)
        self.assertIn("parts", result)
        self.assertIn("magic sword", result["prompt"])

    def test_build_pro_prompt_with_style(self):
        """带风格的 prompt 构建"""
        result = prompt_engine.build_pro_prompt("shield", style="dark")
        self.assertIn("shield", result["prompt"])
        # dark 风格的正面关键词应出现
        self.assertIn("dark fantasy", result["prompt"].lower())

    def test_build_pro_prompt_with_type(self):
        """带资产类型的 prompt 构建"""
        result = prompt_engine.build_pro_prompt("character", asset_type="sprite")
        self.assertIn("character", result["prompt"])
        # sprite 类型的关键词应出现
        self.assertIn("sprite", result["prompt"].lower())

    def test_build_pro_prompt_negative(self):
        """负面 prompt 包含"""
        result = prompt_engine.build_pro_prompt("test", use_negative=True)
        self.assertTrue(len(result["negative"]) > 0)
        self.assertIn("blurry", result["negative"])

    def test_build_pro_prompt_no_negative(self):
        """禁用负面 prompt"""
        result = prompt_engine.build_pro_prompt("test", use_negative=False)
        self.assertEqual(result["negative"], "")

    def test_build_pro_prompt_with_anchor(self):
        """带风格锚点"""
        result = prompt_engine.build_pro_prompt("test", style="pixel", use_anchor=True)
        self.assertIn("consistent color palette", result["prompt"])

    def test_build_pro_prompt_no_anchor(self):
        """禁用风格锚点"""
        result = prompt_engine.build_pro_prompt("test", style="pixel", use_anchor=False)
        self.assertNotIn("consistent color palette", result["prompt"])

    def test_build_pro_prompt_unknown_style(self):
        """未知风格不影响构建"""
        result = prompt_engine.build_pro_prompt("test", style="nonexistent_style")
        # 应该只有 subject，不崩溃
        self.assertIn("test", result["prompt"])

    def test_build_pro_prompt_parts_structure(self):
        """parts 字典包含 subject"""
        result = prompt_engine.build_pro_prompt("dragon", style="dark", asset_type="icon")
        self.assertIn("subject", result["parts"])
        self.assertEqual(result["parts"]["subject"], "dragon")

    def test_get_preset_valid(self):
        """获取存在的预设方案"""
        preset = prompt_engine.get_preset("rpg-weapons")
        self.assertIn("name", preset)
        self.assertIn("prompts", preset)
        self.assertIn("style", preset)
        self.assertEqual(preset["style"], "dark")

    def test_get_preset_invalid(self):
        """获取不存在的预设方案抛出 ValueError"""
        with self.assertRaises(ValueError):
            prompt_engine.get_preset("nonexistent_preset")

    def test_get_preset_error_message(self):
        """错误信息包含可用预设列表"""
        try:
            prompt_engine.get_preset("no_such_preset")
        except ValueError as e:
            self.assertIn("no_such_preset", str(e))
            self.assertIn("rpg-weapons", str(e))

    def test_list_presets(self):
        """列出所有预设方案"""
        presets = prompt_engine.list_presets()
        self.assertIsInstance(presets, list)
        self.assertTrue(len(presets) > 0)

        # 每个预设应包含必要字段
        for p in presets:
            self.assertIn("id", p)
            self.assertIn("name", p)
            self.assertIn("description", p)
            self.assertIn("style", p)
            self.assertIn("asset_type", p)
            self.assertIn("item_count", p)

    def test_list_presets_count(self):
        """预设方案数量与 PRESETS 字典一致"""
        presets = prompt_engine.list_presets()
        self.assertEqual(len(presets), len(prompt_engine.PRESETS))

    def test_all_styles_in_v2(self):
        """所有 V2 风格包含必要字段"""
        for style_name, style_data in prompt_engine.STYLE_KEYWORDS_V2.items():
            self.assertIn("positive", style_data, f"风格 {style_name} 缺少 positive")
            self.assertIn("lighting", style_data, f"风格 {style_name} 缺少 lighting")
            self.assertIn("anchor", style_data, f"风格 {style_name} 缺少 anchor")

    def test_all_types_in_v2(self):
        """所有 V2 资产类型包含必要字段"""
        for type_name, type_data in prompt_engine.TYPE_KEYWORDS_V2.items():
            self.assertIn("positive", type_data, f"类型 {type_name} 缺少 positive")
            self.assertIn("detail", type_data, f"类型 {type_name} 缺少 detail")


if __name__ == "__main__":
    unittest.main()
