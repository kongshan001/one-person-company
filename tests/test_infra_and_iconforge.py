#!/usr/bin/env python3
"""
Unit tests for backup_db, clean_logs, and IconForge

Run: python3 -m unittest tests.test_infra_and_iconforge -v
"""

import hashlib
import os
import shutil
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path


class TestBackupDB(unittest.TestCase):
    """Test database backup utilities"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "infrastructure" / "cron"))
        import importlib
        cls.mod = importlib.import_module("backup_db")

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="backup_test_")
        self.backup_dir = os.path.join(self.test_dir, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_backup_regular_file(self):
        """Test backing up a regular file"""
        src = os.path.join(self.test_dir, "test.txt")
        with open(src, "w") as f:
            f.write("hello backup")
        dest = self.mod.backup_file(src, self.backup_dir)
        self.assertTrue(os.path.exists(dest))
        with open(dest) as f:
            self.assertEqual(f.read(), "hello backup")
        # Check SHA256 checksum file exists
        self.assertTrue(os.path.exists(dest + ".sha256"))

    def test_backup_sqlite_file(self):
        """Test backing up a SQLite database"""
        src = os.path.join(self.test_dir, "test.db")
        conn = sqlite3.connect(src)
        conn.execute("CREATE TABLE t (x TEXT)")
        conn.execute("INSERT INTO t VALUES ('data')")
        conn.commit()
        conn.close()
        dest = self.mod.backup_file(src, self.backup_dir)
        self.assertTrue(os.path.exists(dest))
        # Verify backup is readable
        backup_conn = sqlite3.connect(dest)
        rows = backup_conn.execute("SELECT * FROM t").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "data")
        backup_conn.close()

    def test_sha256_checksum_correctness(self):
        """Test SHA256 checksum is correct"""
        src = os.path.join(self.test_dir, "checksum_test.txt")
        content = b"verify this content"
        with open(src, "wb") as f:
            f.write(content)
        expected = hashlib.sha256(content).hexdigest()
        actual = self.mod._sha256_file(src)
        self.assertEqual(actual, expected)

    def test_backup_creates_directory(self):
        """Test that backup creates destination directory if needed"""
        src = os.path.join(self.test_dir, "testdata.txt")
        with open(src, "w") as f:
            f.write("test")
        new_backup_dir = os.path.join(self.test_dir, "nested", "backups")
        dest = self.mod.backup_file(src, new_backup_dir)
        self.assertTrue(os.path.exists(dest))

    def test_cleanup_old_removes_expired(self):
        """Test cleanup of old backups"""
        old_file = os.path.join(self.backup_dir, "old_backup.txt")
        with open(old_file, "w") as f:
            f.write("old data")
        old_time = time.time() - (31 * 86400)
        os.utime(old_file, (old_time, old_time))
        new_file = os.path.join(self.backup_dir, "new_backup.txt")
        with open(new_file, "w") as f:
            f.write("new data")
        self.mod.cleanup_old(self.backup_dir, 30)
        self.assertFalse(os.path.exists(old_file))
        self.assertTrue(os.path.exists(new_file))

    def test_backup_with_prefix(self):
        """Test backup with custom prefix"""
        # Use a .txt file (not .db) to avoid SQLite backup API trying to read it
        src = os.path.join(self.test_dir, "datafile.txt")
        with open(src, "w") as f:
            f.write("data")
        dest = self.mod.backup_file(src, self.backup_dir, "pre_")
        basename = os.path.basename(dest)
        self.assertTrue(basename.startswith("pre_"))


class TestCleanLogs(unittest.TestCase):
    """Test log cleanup utilities"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "infrastructure" / "cron"))
        import importlib
        cls.mod = importlib.import_module("clean_logs")

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="logs_test_")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_clean_removes_old_logs(self):
        """Test removing old log files"""
        old_log = os.path.join(self.test_dir, "app.log")
        with open(old_log, "w") as f:
            f.write("old log content\n" * 100)
        old_time = time.time() - (8 * 86400)
        os.utime(old_log, (old_time, old_time))
        self.mod.clean_logs(self.test_dir, 7, False)
        self.assertFalse(os.path.exists(old_log))

    def test_clean_keeps_recent_logs(self):
        """Test keeping recent log files"""
        recent_log = os.path.join(self.test_dir, "recent.log")
        with open(recent_log, "w") as f:
            f.write("recent content")
        self.mod.clean_logs(self.test_dir, 7, False)
        self.assertTrue(os.path.exists(recent_log))

    def test_dry_run_does_not_delete(self):
        """Test dry run mode doesn't actually delete"""
        old_log = os.path.join(self.test_dir, "old.log")
        with open(old_log, "w") as f:
            f.write("old")
        old_time = time.time() - (8 * 86400)
        os.utime(old_log, (old_time, old_time))
        self.mod.clean_logs(self.test_dir, 7, True)
        self.assertTrue(os.path.exists(old_log))

    def test_nonexistent_directory(self):
        """Test cleaning a directory that doesn't exist"""
        self.mod.clean_logs("/tmp/nonexistent_dir_12345", 7)


class TestIconForge(unittest.TestCase):
    """Test IconForge generate utilities"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "products" / "icon-forge"))
        import importlib
        cls.mod = importlib.import_module("generate")

    def test_style_keywords_defined(self):
        """Test that style keywords are properly defined"""
        styles = self.mod.STYLE_KEYWORDS
        self.assertIsInstance(styles, dict)
        self.assertIn("pixel", styles)
        self.assertIn("cartoon", styles)
        self.assertIn("realistic", styles)

    def test_type_keywords_defined(self):
        """Test that type keywords are properly defined"""
        types = self.mod.TYPE_KEYWORDS
        self.assertIsInstance(types, dict)
        self.assertIn("icon", types)
        self.assertIn("sprite", types)

    def test_sizes_defined(self):
        """Test that sizes are properly defined"""
        sizes = self.mod.SIZES
        self.assertIsInstance(sizes, list)
        self.assertGreater(len(sizes), 0)
        self.assertIn(512, sizes)

    def test_build_prompt(self):
        """Test prompt building for AI generation"""
        prompt = self.mod.build_prompt("sword", style="pixel", asset_type="icon")
        self.assertIn("sword", prompt)
        self.assertIn("pixel", prompt.lower())

    def test_build_prompt_no_style(self):
        """Test prompt building without style"""
        prompt = self.mod.build_prompt("shield", style=None, asset_type="icon")
        self.assertIn("shield", prompt)

    def test_quality_check_missing_file(self):
        """Test quality check on non-existent file raises FileNotFoundError"""
        with self.assertRaises(FileNotFoundError):
            self.mod.quality_check("/tmp/nonexistent_icon_12345.png", expected_size=512)

    def test_generate_image_callable(self):
        """Test image generation function exists and is callable"""
        self.assertTrue(callable(self.mod.generate_image))


if __name__ == "__main__":
    unittest.main()
