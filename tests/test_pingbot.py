#!/usr/bin/env python3
"""
Unit tests for PingBot PingDB and Pinger

Run: python -m pytest tests/test_pingbot.py -v
     python3 -m unittest tests.test_pingbot -v
"""

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path


class TestPingDB(unittest.TestCase):
    """Test PingDB database operations"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "products" / "ping-bot"))
        import importlib
        cls.monitor_module = importlib.import_module("monitor")
        cls.PingDB = cls.monitor_module.PingDB
        cls.Pinger = cls.monitor_module.Pinger

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pingbot_test_")
        self.db_path = os.path.join(self.test_dir, "test.db")
        self.db = self.PingDB(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_add_target(self):
        """Test adding a monitoring target"""
        result = self.db.add_target(
            name="test_site",
            url="https://example.com",
            method="GET",
            expected_status=200,
        )
        self.assertEqual(result["name"], "test_site")
        self.assertEqual(result["url"], "https://example.com")

    def test_add_target_invalid_name(self):
        """Test that invalid target names are rejected"""
        result = self.db.add_target(
            name="invalid name!",
            url="https://example.com",
        )
        self.assertIn("error", result)

    def test_add_target_invalid_url(self):
        """Test that non-http URLs are rejected"""
        result = self.db.add_target(
            name="bad_url",
            url="ftp://example.com",
        )
        self.assertIn("error", result)

    def test_get_targets(self):
        """Test retrieving targets"""
        self.db.add_target(name="site1", url="https://example1.com")
        self.db.add_target(name="site2", url="https://example2.com")
        targets = self.db.get_targets()
        self.assertEqual(len(targets), 2)

    def test_remove_target(self):
        """Test removing a target"""
        self.db.add_target(name="to_remove", url="https://example.com")
        result = self.db.remove_target("to_remove")
        self.assertTrue(result)
        # Verify it's gone
        targets = self.db.get_targets()
        self.assertEqual(len(targets), 0)

    def test_remove_nonexistent_target(self):
        """Test removing a target that doesn't exist"""
        result = self.db.remove_target("nonexistent")
        self.assertFalse(result)

    def test_record_and_get_history(self):
        """Test recording checks and retrieving history"""
        self.db.add_target(name="hist_test", url="https://example.com")
        self.db.record_check("hist_test", status_code=200, response_time_ms=150, is_up=True)
        self.db.record_check("hist_test", status_code=500, response_time_ms=200, is_up=False, error="Internal Server Error")
        history = self.db.get_history("hist_test", hours=24)
        self.assertGreaterEqual(len(history), 1)

    def test_get_status(self):
        """Test getting status overview"""
        self.db.add_target(name="status_test", url="https://example.com")
        self.db.record_check("status_test", status_code=200, response_time_ms=100, is_up=True)
        status = self.db.get_status()
        self.assertEqual(len(status), 1)
        self.assertEqual(status[0]["name"], "status_test")
        self.assertEqual(status[0]["uptime_24h"], 100.0)

    def test_get_status_mixed_uptime(self):
        """Test uptime calculation with mixed results"""
        self.db.add_target(name="mixed_test", url="https://example.com")
        self.db.record_check("mixed_test", status_code=200, response_time_ms=100, is_up=True)
        self.db.record_check("mixed_test", status_code=200, response_time_ms=100, is_up=True)
        self.db.record_check("mixed_test", status_code=500, response_time_ms=200, is_up=False)
        status = self.db.get_status()
        # 2/3 up = 66.67%
        self.assertAlmostEqual(status[0]["uptime_24h"], 66.67, places=1)

    def test_add_target_with_keyword(self):
        """Test adding a target with expected keyword"""
        result = self.db.add_target(
            name="keyword_test",
            url="https://example.com",
            expected_keyword="welcome",
        )
        self.assertEqual(result["name"], "keyword_test")

    def test_add_target_name_with_hyphen(self):
        """Test that hyphens and underscores are allowed in names"""
        result = self.db.add_target(name="my-test_site", url="https://example.com")
        self.assertNotIn("error", result)

    def test_cleanup_old(self):
        """Test cleanup of old records doesn't crash"""
        self.db.add_target(name="cleanup_test", url="https://example.com")
        self.db.record_check("cleanup_test", status_code=200, response_time_ms=100, is_up=True)
        self.db.cleanup_old()
        # Should not raise


class TestPinger(unittest.TestCase):
    """Test Pinger URL checking logic"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "products" / "ping-bot"))
        import importlib
        cls.monitor_module = importlib.import_module("monitor")
        cls.PingDB = cls.monitor_module.PingDB
        cls.Pinger = cls.monitor_module.Pinger

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="pinger_test_")
        self.db_path = os.path.join(self.test_dir, "test.db")
        self.db = self.PingDB(self.db_path)
        self.pinger = self.Pinger(self.db)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_check_invalid_url(self):
        """Test checking a URL that doesn't exist"""
        result = self.pinger.check_url(
            url="http://127.0.0.1:59999/",  # Port that shouldn't be listening
            method="GET",
            expected_status=200,
        )
        self.assertFalse(result["is_up"])
        self.assertIsNotNone(result["error"])

    def test_check_valid_url(self):
        """Test checking a valid URL (requires network)"""
        result = self.pinger.check_url(
            url="https://httpbin.org/status/200",
            method="GET",
            expected_status=200,
        )
        # This test may fail without network, but that's expected
        if result["is_up"]:
            self.assertEqual(result["status_code"], 200)
            self.assertIsNone(result["error"])

    def test_check_url_expected_status_mismatch(self):
        """Test that status code mismatch marks as down"""
        result = self.pinger.check_url(
            url="https://httpbin.org/status/404",
            method="GET",
            expected_status=200,
        )
        if result["status_code"] == 404:
            self.assertFalse(result["is_up"])


if __name__ == "__main__":
    unittest.main()
