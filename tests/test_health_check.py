#!/usr/bin/env python3
"""
Unit tests for health_check module

Run: python3 -m unittest tests.test_health_check -v
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path


class TestHealthCheck(unittest.TestCase):
    """Test health check functions"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "infrastructure" / "monitoring"))
        import importlib
        cls.mod = importlib.import_module("health_check")

    def test_check_http_invalid_url(self):
        """Test HTTP check with unreachable URL"""
        result = self.mod.check_http("http://127.0.0.1:59999/nonexistent", timeout=2)
        self.assertEqual(result["status"], "down")
        self.assertIn("error", result)

    def test_check_disk(self):
        """Test disk space check"""
        result = self.mod.check_disk(path="/", threshold_gb=0.001)
        self.assertIn("status", result)
        self.assertIn("total_gb", result)
        self.assertIn("free_gb", result)
        self.assertIn("used_pct", result)

    def test_check_memory(self):
        """Test memory check"""
        result = self.mod.check_memory()
        self.assertIn("status", result)

    def test_check_http_valid_url(self):
        """Test HTTP check with a reachable URL (network dependent)"""
        result = self.mod.check_http("https://httpbin.org/status/200", timeout=10)
        if result["status"] == "up":
            self.assertEqual(result["code"], 200)


class TestHealthCheckIntegration(unittest.TestCase):
    """Integration tests for full health check run"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "infrastructure" / "monitoring"))
        import importlib
        cls.mod = importlib.import_module("health_check")

    def test_run_checks(self):
        """Test running all health checks"""
        if hasattr(self.mod, "run_checks"):
            results = self.mod.run_checks()
            self.assertIsInstance(results, dict)

    def test_print_report(self):
        """Test result printing doesn't crash with valid structure"""
        if hasattr(self.mod, "print_report"):
            # Provide all required keys matching the actual print_report structure
            self.mod.print_report({
                "overall": "healthy",
                "hostname": "test",
                "timestamp": "2026-01-01T00:00:00Z",
                "system": {},
                "services": {},
                "checks": [],
            })


if __name__ == "__main__":
    unittest.main()
