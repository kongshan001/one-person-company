#!/usr/bin/env python3
"""
Unit tests for export_data and deploy modules

Run: python -m pytest tests/test_export_deploy.py -v
     python3 -m unittest tests.test_export_deploy -v
"""

import gzip
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestExportPasteHut(unittest.TestCase):
    """Test export_pastehut function"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "infrastructure" / "cron"))
        sys.path.insert(0, str(project_root))
        import importlib
        cls.export_module = importlib.import_module("export_data")

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="export_test_")
        self.output_dir = Path(self.test_dir) / "output"
        self.output_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _export_pastehut(self, output_dir, pretty=False):
        return self.export_module.export_pastehut(output_dir, pretty=pretty)

    def _export_pingbot(self, output_dir, pretty=False):
        return self.export_module.export_pingbot(output_dir, pretty=pretty)

    def test_export_no_data(self):
        """Export should return no_data when meta.json doesn't exist"""
        from config import PasteHutConfig
        with patch.object(PasteHutConfig, 'DATA_DIR', self.test_dir):
            result = self._export_pastehut(self.output_dir)
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["records"], 0)

    def test_export_with_data(self):
        """Export should create JSON file with paste data"""
        from config import PasteHutConfig
        # Create fake data directory
        data_dir = Path(self.test_dir) / "data"
        data_dir.mkdir()
        meta = {
            "abc123": {
                "id": "abc123",
                "title": "Test Paste",
                "syntax": "python",
                "size": 100,
            }
        }
        meta_file = data_dir / "meta.json"
        meta_file.write_text(json.dumps(meta))
        content_file = data_dir / "abc123.txt"
        content_file.write_text("print('hello')")

        with patch.object(PasteHutConfig, 'DATA_DIR', str(data_dir)):
            result = self._export_pastehut(self.output_dir)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["records"], 1)
        self.assertIsNotNone(result["file"])

        # Verify exported file
        export_file = Path(result["file"])
        self.assertTrue(export_file.exists())
        with open(export_file) as f:
            data = json.load(f)
        self.assertEqual(data["product"], "pastehut")
        self.assertEqual(data["total_pastes"], 1)
        self.assertEqual(len(data["pastes"]), 1)
        self.assertEqual(data["pastes"][0]["content"], "print('hello')")

    def test_export_pretty(self):
        """Export with pretty=True should produce indented JSON"""
        from config import PasteHutConfig
        data_dir = Path(self.test_dir) / "data"
        data_dir.mkdir()
        meta = {"abc123": {"id": "abc123", "title": "Test"}}
        (data_dir / "meta.json").write_text(json.dumps(meta))
        (data_dir / "abc123.txt").write_text("hello")

        with patch.object(PasteHutConfig, 'DATA_DIR', str(data_dir)):
            result = self._export_pastehut(self.output_dir, pretty=True)

        self.assertEqual(result["status"], "ok")
        with open(result["file"]) as f:
            content = f.read()
        # Pretty JSON should have indentation
        self.assertIn("\n", content)
        self.assertIn("  ", content)


class TestExportPingBot(unittest.TestCase):
    """Test export_pingbot function"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "infrastructure" / "cron"))
        sys.path.insert(0, str(project_root))
        import importlib
        cls.export_module = importlib.import_module("export_data")

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="export_test_")
        self.output_dir = Path(self.test_dir) / "output"
        self.output_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _export_pingbot(self, output_dir, pretty=False):
        return self.export_module.export_pingbot(output_dir, pretty=pretty)

    def test_export_no_db(self):
        """Export should return no_data when DB doesn't exist"""
        from config import PingBotConfig
        with patch.object(PingBotConfig, 'DB_PATH', "/tmp/nonexistent.db"):
            result = self._export_pingbot(self.output_dir)
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["records"], 0)

    def test_export_with_data(self):
        """Export should create JSON with targets and checks"""
        from config import PingBotConfig
        db_path = os.path.join(self.test_dir, "test.db")
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE targets (
                name TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                method TEXT DEFAULT 'GET',
                expected_status INTEGER DEFAULT 200,
                expected_keyword TEXT,
                interval INTEGER DEFAULT 60,
                enabled INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_name TEXT NOT NULL,
                status_code INTEGER,
                response_time_ms INTEGER,
                is_up INTEGER,
                error TEXT,
                checked_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.execute("INSERT INTO targets (name, url) VALUES (?, ?)", ("test_site", "https://example.com"))
        conn.execute("INSERT INTO checks (target_name, status_code, response_time_ms, is_up) VALUES (?, ?, ?, ?)",
                      ("test_site", 200, 150, 1))
        conn.commit()
        conn.close()

        with patch.object(PingBotConfig, 'DB_PATH', db_path):
            result = self._export_pingbot(self.output_dir)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["records"], 2)  # 1 target + 1 check

        export_file = Path(result["file"])
        self.assertTrue(export_file.exists())
        with open(export_file) as f:
            data = json.load(f)
        self.assertEqual(data["product"], "pingbot")
        self.assertEqual(len(data["targets"]), 1)
        self.assertEqual(len(data["checks"]), 1)
        self.assertEqual(data["targets"][0]["name"], "test_site")


class TestCompressFile(unittest.TestCase):
    """Test compress_file function"""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="compress_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_compress_creates_gz(self):
        """compress_file should create a .gz file and delete original"""
        test_file = os.path.join(self.test_dir, "test.json")
        with open(test_file, "w") as f:
            json.dump({"key": "value"}, f)

        from infrastructure.cron.export_data import compress_file
        result = compress_file(test_file)
        self.assertTrue(result.endswith(".gz"))
        self.assertTrue(os.path.exists(result))
        self.assertFalse(os.path.exists(test_file))

        # Verify gzip content
        with gzip.open(result, "rt") as f:
            data = json.load(f)
        self.assertEqual(data["key"], "value")


class TestDeployHelpers(unittest.TestCase):
    """Test deploy.py helper functions"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "infrastructure" / "deploy"))
        sys.path.insert(0, str(project_root))
        import importlib
        cls.deploy_module = importlib.import_module("deploy")

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="deploy_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_pid_no_file(self):
        """get_pid should return None when PID file doesn't exist"""
        with patch.object(self.deploy_module, 'PID_DIR', Path(self.test_dir)):
            result = self.deploy_module.get_pid("nonexistent")
        self.assertIsNone(result)

    def test_get_pid_with_file(self):
        """get_pid should return PID from file"""
        pid_dir = Path(self.test_dir)
        (pid_dir / "test_service.pid").write_text("12345")
        with patch.object(self.deploy_module, 'PID_DIR', pid_dir):
            result = self.deploy_module.get_pid("test_service")
        self.assertEqual(result, 12345)

    def test_get_pid_invalid_content(self):
        """get_pid should return None for invalid PID file content"""
        pid_dir = Path(self.test_dir)
        (pid_dir / "bad.pid").write_text("not_a_number")
        with patch.object(self.deploy_module, 'PID_DIR', pid_dir):
            result = self.deploy_module.get_pid("bad")
        self.assertIsNone(result)

    def test_is_running_none(self):
        """is_running should return False for None PID"""
        self.assertFalse(self.deploy_module.is_running(None))

    def test_is_running_current_process(self):
        """is_running should return True for current process PID"""
        self.assertTrue(self.deploy_module.is_running(os.getpid()))

    def test_is_running_nonexistent(self):
        """is_running should return False for non-existent PID"""
        self.assertFalse(self.deploy_module.is_running(999999999))


class TestPasteHutTags(unittest.TestCase):
    """Test PasteHut tags system"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "products" / "paste-hut"))
        import importlib
        cls.server_module = importlib.import_module("server")
        cls.PasteStore = cls.server_module.PasteStore

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pastehut_tags_")
        self.store = self.PasteStore(self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_with_tags(self):
        """Create paste with tags should store them in metadata"""
        result = self.store.create(
            content="tagged content",
            title="Tagged Paste",
            syntax="python",
            tags=["python", "tutorial", "api"],
        )
        self.assertIn("tags", result)
        self.assertEqual(result["tags"], ["python", "tutorial", "api"])

    def test_create_with_no_tags(self):
        """Create paste without tags should have empty list"""
        result = self.store.create(
            content="no tags content",
            title="No Tags",
        )
        self.assertIn("tags", result)
        self.assertEqual(result["tags"], [])

    def test_tags_normalized_to_lowercase(self):
        """Tags should be normalized to lowercase"""
        result = self.store.create(
            content="case test",
            tags=["Python", "API", "Tutorial"],
        )
        self.assertEqual(result["tags"], ["python", "api", "tutorial"])

    def test_tags_deduplication(self):
        """Duplicate tags should be removed"""
        result = self.store.create(
            content="dup test",
            tags=["python", "Python", "PYTHON"],
        )
        self.assertEqual(result["tags"], ["python"])

    def test_tags_max_five(self):
        """Only first 5 tags should be kept"""
        result = self.store.create(
            content="many tags",
            tags=["a", "b", "c", "d", "e", "f", "g"],
        )
        self.assertEqual(len(result["tags"]), 5)
        self.assertEqual(result["tags"], ["a", "b", "c", "d", "e"])

    def test_tags_invalid_characters_filtered(self):
        """Tags with special characters should be filtered"""
        result = self.store.create(
            content="filter test",
            tags=["valid-tag", "invalid tag!", "also_valid", ""],
        )
        # "invalid tag!" has space and !, should be filtered
        # empty string should be filtered
        self.assertIn("valid-tag", result["tags"])
        self.assertIn("also_valid", result["tags"])
        self.assertEqual(len(result["tags"]), 2)

    def test_tags_max_length_32(self):
        """Tags longer than 32 chars should be filtered"""
        long_tag = "a" * 33
        result = self.store.create(
            content="long tag test",
            tags=[long_tag, "short"],
        )
        self.assertNotIn(long_tag, result["tags"])
        self.assertIn("short", result["tags"])

    def test_non_string_tags_ignored(self):
        """Non-string tags should be silently ignored"""
        result = self.store.create(
            content="type test",
            tags=[123, None, "valid", True],
        )
        self.assertEqual(result["tags"], ["valid"])

    def test_list_by_tag(self):
        """list_by_tag should return pastes matching the tag"""
        self.store.create(content="python1", tags=["python", "web"])
        self.store.create(content="python2", tags=["python", "api"])
        self.store.create(content="javascript1", tags=["javascript"])

        result = self.store.list_by_tag("python")
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["tag"], "python")
        self.assertEqual(len(result["pastes"]), 2)

    def test_list_by_tag_case_insensitive(self):
        """list_by_tag should be case insensitive"""
        self.store.create(content="test", tags=["Python"])
        result = self.store.list_by_tag("PYTHON")
        self.assertEqual(result["total"], 1)

    def test_list_by_tag_empty(self):
        """list_by_tag with no matches should return empty"""
        self.store.create(content="test", tags=["python"])
        result = self.store.list_by_tag("nonexistent")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["pastes"], [])

    def test_get_all_tags(self):
        """get_all_tags should return all tags with counts"""
        self.store.create(content="a", tags=["python", "web"])
        self.store.create(content="b", tags=["python"])
        self.store.create(content="c", tags=["javascript", "web"])

        result = self.store.get_all_tags()
        self.assertEqual(result["unique_count"], 3)

        tags_map = {t["name"]: t["count"] for t in result["tags"]}
        self.assertEqual(tags_map["python"], 2)
        self.assertEqual(tags_map["web"], 2)
        self.assertEqual(tags_map["javascript"], 1)

    def test_tags_in_list_recent(self):
        """Tags should appear in list_recent output"""
        self.store.create(content="tagged", title="Tagged", tags=["test"])
        result = self.store.list_recent(limit=10)
        self.assertEqual(len(result["pastes"]), 1)
        self.assertIn("tags", result["pastes"][0])
        self.assertEqual(result["pastes"][0]["tags"], ["test"])

    def test_tags_persist_across_reload(self):
        """Tags should survive store reload from disk"""
        result = self.store.create(
            content="persist test",
            title="Persist",
            tags=["persistent"],
        )
        paste_id = result["id"]

        # Reload store from same directory
        store2 = self.PasteStore(self.test_dir)
        loaded = store2.get(paste_id)
        self.assertIsNotNone(loaded)
        self.assertIn("persistent", loaded.get("tags", []))


if __name__ == "__main__":
    unittest.main()
