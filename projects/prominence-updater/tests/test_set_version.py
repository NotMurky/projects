import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from app import make_handler
from http.server import ThreadingHTTPServer


class SetVersionEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.config = base / "config.json"
        self.server_root = base / "server"
        # A mods dir with a jar so auto-detect returns a real version
        (self.server_root / "mods").mkdir(parents=True)
        (self.server_root / "mods" / "Prominent-GLOBAL-MC1.20.1-4.0.2.jar").write_bytes(b"x")
        self.maint_cfg = base / "maintenance.yml"
        self.maint_cfg.write_text("maintenance-enabled: false\n")
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(
                self.server_root,
                self.config,
                base / "staging",
                velocity_maintenance_config=self.maint_cfg,
            ),
        )
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.thread.join()
        self.httpd.server_close()
        self.temp.cleanup()

    def request(self, method, path, body=b"", headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port)
        conn.request(method, path, body, headers or {})
        response = conn.getresponse()
        data = response.read()
        conn.close()
        return response.status, data, dict(response.getheaders())

    def _post_version(self, value):
        body = f"version={value}".encode()
        return self.request(
            "POST", "/set-version", body,
            {"Content-Type": "application/x-www-form-urlencoded"},
        )

    def test_default_reports_detected_version(self):
        status, body, _ = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"v4.0.2", body)

    def test_manual_override_wins_over_jar(self):
        status, _, _ = self._post_version("4.0.3")
        self.assertEqual(status, 303)
        state = json.loads(self.config.read_text())
        self.assertEqual(state["installed_version_override"], "4.0.3")
        self.assertEqual(state["installed_version"], "4.0.3")
        # Dashboard shows the override, flagged manual
        _, body, _ = self.request("GET", "/")
        self.assertIn(b"v4.0.3", body)
        self.assertIn(b"(manual)", body)

    def test_hf_suffix_accepted(self):
        status, _, _ = self._post_version("4.0.3hf")
        self.assertEqual(status, 303)
        state = json.loads(self.config.read_text())
        self.assertEqual(state["installed_version_override"], "4.0.3hf")

    def test_invalid_version_rejected(self):
        status, _, _ = self._post_version("not-a-version")
        self.assertEqual(status, 400)
        state = json.loads(self.config.read_text())
        self.assertIsNone(state.get("installed_version_override"))

    def test_blank_clears_override_reverts_to_detected(self):
        self._post_version("4.0.3")
        # Now clear it
        status, _, _ = self._post_version("")
        self.assertEqual(status, 303)
        state = json.loads(self.config.read_text())
        self.assertIsNone(state["installed_version_override"])
        self.assertEqual(state["installed_version"], "4.0.2")
        _, body, _ = self.request("GET", "/")
        self.assertIn(b"v4.0.2", body)
        self.assertNotIn(b"(manual)", body)


if __name__ == "__main__":
    unittest.main()
