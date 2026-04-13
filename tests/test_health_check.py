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


class TestPrometheusFormat(unittest.TestCase):
    """Test Prometheus exposition format output"""

    @classmethod
    def setUpClass(cls):
        project_root = Path(__file__).parent.parent
        import sys
        sys.path.insert(0, str(project_root / "infrastructure" / "monitoring"))
        import importlib
        cls.mod = importlib.import_module("health_check")

    def test_format_prometheus_healthy(self):
        """Test Prometheus output for healthy system"""
        results = {
            "overall": "healthy",
            "services": {
                "PasteHut": {"status": "up"},
                "PingBot": {"status": "ok"},
            },
            "system": {
                "disk": {"free_gb": 10.0, "used_pct": 45.2},
                "memory": {"available_mb": 2048.0, "used_pct": 62.3},
                "load": {"load_1m": 0.52},
            },
        }
        output = self.mod.format_prometheus(results)
        self.assertIn("opc_system_up 1", output)
        self.assertIn('opc_service_up{service="PasteHut"} 1', output)
        self.assertIn('opc_service_up{service="PingBot"} 1', output)
        self.assertIn("opc_disk_free_bytes", output)
        self.assertIn("opc_disk_used_pct 45.2", output)
        self.assertIn("opc_memory_available_bytes", output)
        self.assertIn("opc_memory_used_pct 62.3", output)
        self.assertIn("opc_load_1m 0.52", output)

    def test_format_prometheus_degraded(self):
        """Test Prometheus output for degraded system"""
        results = {
            "overall": "degraded",
            "services": {
                "PasteHut": {"status": "down"},
            },
            "system": {},
        }
        output = self.mod.format_prometheus(results)
        self.assertIn("opc_system_up 0", output)
        self.assertIn('opc_service_up{service="PasteHut"} 0', output)

    def test_format_prometheus_empty_services(self):
        """Test Prometheus output with no services"""
        results = {
            "overall": "healthy",
            "services": {},
            "system": {},
        }
        output = self.mod.format_prometheus(results)
        self.assertIn("opc_system_up 1", output)
        # Should still have HELP/TYPE for service_up but no data lines
        self.assertIn("# HELP opc_service_up", output)

    def test_format_prometheus_has_help_and_type(self):
        """Test that each metric has HELP and TYPE annotations"""
        results = {
            "overall": "healthy",
            "services": {"TestSvc": {"status": "up"}},
            "system": {
                "disk": {"free_gb": 5.0, "used_pct": 50.0},
                "memory": {"available_mb": 1024.0, "used_pct": 40.0},
                "load": {"load_1m": 1.0},
            },
        }
        output = self.mod.format_prometheus(results)
        # Every metric line should be preceded by # HELP and # TYPE
        for metric in ["opc_system_up", "opc_service_up", "opc_disk_free_bytes",
                        "opc_disk_used_pct", "opc_memory_available_bytes",
                        "opc_memory_used_pct", "opc_load_1m"]:
            self.assertIn(f"# HELP {metric}", output)
            self.assertIn(f"# TYPE {metric}", output)

    def test_format_prometheus_partial_system(self):
        """Test Prometheus output with partial system info (no memory/load)"""
        results = {
            "overall": "healthy",
            "services": {},
            "system": {"disk": {"used_pct": 30.0}},
        }
        output = self.mod.format_prometheus(results)
        self.assertIn("opc_system_up 1", output)
        self.assertIn("opc_disk_used_pct 30.0", output)
        # Should NOT have memory or load metrics
        self.assertNotIn("opc_memory_available_bytes", output)
        self.assertNotIn("opc_load_1m", output)


if __name__ == "__main__":
    unittest.main()
