import http.client
import io
import json
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path

from app import make_handler
from http.server import ThreadingHTTPServer


def zip_bytes():
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as archive:
        archive.writestr("mods/new.jar", b"new")
        archive.writestr("server.properties", b"must not stage")
    return blob.getvalue()


def multipart(field, filename, body, boundary="BOUNDARY"):
    return (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{field}\"; filename=\"{filename}\"\r\n"
        f"Content-Type: application/zip\r\n\r\n"
    ).encode() + body + f"\r\n--{boundary}--\r\n".encode()


class UploadEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.config = base / "config.json"
        self.server_root = base / "server"
        self.server_root.mkdir()
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

    def _upload(self, auth_headers=None):
        payload = multipart("archive", "Prominence-II-v3.2.1.zip", zip_bytes())
        h = {"Content-Type": "multipart/form-data; boundary=BOUNDARY", "Content-Length": str(len(payload))}
        if auth_headers:
            h.update(auth_headers)
        return self.request("POST", "/upload", payload, h)

    def test_authenticated_handler_refuses_anonymous_upload(self):
        # Rebuild server with auth token
        self.httpd.shutdown()
        self.thread.join()
        self.httpd.server_close()
        base = Path(self.temp.name)
        self.httpd = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(
                self.server_root,
                self.config,
                base / "staging",
                auth_token="test-token",
                velocity_maintenance_config=self.maint_cfg,
            ),
        )
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.start()

        status, _, _ = self._upload()
        self.assertEqual(status, 401)

        status, _, headers = self._upload({"Authorization": "Bearer test-token"})
        # Now returns 303 redirect on success
        self.assertEqual(status, 303)

    def test_zip_upload_inspects_and_tracks_candidate_without_touching_server(self):
        status, _, headers = self._upload()
        # Redirects on success
        self.assertEqual(status, 303)
        # Candidate saved to config
        state = json.loads(self.config.read_text())
        self.assertEqual(state["candidate_version"], "3.2.1")
        self.assertEqual(state["candidate_archive"], "Prominence-II-v3.2.1.zip")
        # Archive stored in uploads/
        self.assertTrue(
            (Path(self.temp.name) / "staging" / "uploads" / "Prominence-II-v3.2.1.zip").exists()
        )
        # Live server NOT touched
        self.assertFalse((self.server_root / "mods" / "new.jar").exists())

    def test_stage_requires_explicit_candidate_confirmation_and_remains_non_live(self):
        self._upload()
        # Wrong confirmation → 400
        status, _, _ = self.request(
            "POST", "/stage", b"confirm=wrong",
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(status, 400)

        # Correct confirmation → redirect
        status, _, _ = self.request(
            "POST", "/stage", b"confirm=STAGE+3.2.1",
            {"Content-Type": "application/x-www-form-urlencoded"},
        )
        self.assertEqual(status, 303)
        # Live server still untouched
        self.assertFalse((self.server_root / "mods" / "new.jar").exists())


if __name__ == "__main__":
    unittest.main()
