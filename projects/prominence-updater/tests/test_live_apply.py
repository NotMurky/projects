"""Tests for the live_apply_archive workflow using injected fakes."""
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from updater_core import (
    CraftyControl,
    UnsafeArchiveError,
    VelocityMaintenanceToggle,
    live_apply_archive,
)


def make_zip(entries: dict[str, str]) -> bytes:
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return blob.getvalue()


def fake_crafty(players: int = 0, running: bool = True) -> CraftyControl:
    crafty = MagicMock(spec=CraftyControl)
    crafty.player_count.return_value = players
    crafty.is_running.return_value = running
    crafty.restart.return_value = None
    crafty.wait_for_running.return_value = None
    crafty.stats.return_value = {"running": running, "online": players}
    return crafty


class LiveApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "server"; self.root.mkdir()
        (self.root / "mods").mkdir()
        (self.root / "mods" / "Prominent-GLOBAL-MC1.20.1-3.9.21.jar").write_text("old")
        (self.root / "server.properties").write_text("motd=old\n")
        # Dontdeleteimportantmods with custom mods
        overlay = self.root / "Dontdeleteimportantmods"
        (overlay / "mods").mkdir(parents=True)
        (overlay / "config").mkdir(parents=True)
        (overlay / "mods" / "yeptwo.jar").write_text("custom")
        (overlay / "mods" / "darktimer.jar").write_text("custom")
        (overlay / "config" / "fabricproxy.yml").write_text("config")
        self.staging = base / "staging"
        self.backup_root = base / "backups"
        # Create a valid pack archive
        self.archive = base / "Prominence-II-4.0.3.zip"
        self.archive.write_bytes(make_zip({
            "mods/Prominent-GLOBAL-MC1.20.1-4.0.3.jar": "new",
            "mods/somemod.jar": "data",
            "config/pack.json": "{}",
            "server.properties": "must not install",  # protected
            "fabric.jar": "must not install",          # protected
        }))
        # Velocity maintenance config
        self.maint_cfg = base / "maintenance.yml"
        self.maint_cfg.write_text("maintenance-enabled: false\n")
        # MiniMOTD conf
        self.minimotd = base / "main.conf"
        self.minimotd.write_text(
            'motds=[{line1="server" line2="<b>Modded | <green>V3.9.21</green></b>"}]\n'
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _apply(self, force=False, players=0):
        crafty = fake_crafty(players=players)
        maint = VelocityMaintenanceToggle(self.maint_cfg)
        return live_apply_archive(
            archive_path=self.archive,
            root=self.root,
            staging_root=self.staging,
            backup_root=self.backup_root,
            crafty=crafty,
            maintenance=maint,
            minimotd_conf=self.minimotd,
            candidate_version="4.0.3",
            user_protected=None,
            force=force,
            overlay_dir_name="Dontdeleteimportantmods",
        )

    def test_successful_apply_installs_files_and_returns_ok(self):
        result = self._apply()
        self.assertTrue(result.success)
        self.assertEqual(result.installed_version, "4.0.3")
        self.assertTrue((self.root / "mods" / "Prominent-GLOBAL-MC1.20.1-4.0.3.jar").exists())

    def test_server_properties_never_changed(self):
        self._apply()
        self.assertIn("motd=old", (self.root / "server.properties").read_text())

    def test_fabric_jar_never_changed(self):
        self._apply()
        # fabric.jar was not in archive install list so it is untouched
        self.assertFalse((self.root / "fabric.jar").exists())

    def test_custom_mods_overlaid_after_pack_update(self):
        self._apply()
        self.assertEqual((self.root / "mods" / "yeptwo.jar").read_text(), "custom")
        self.assertEqual((self.root / "mods" / "darktimer.jar").read_text(), "custom")
        self.assertEqual((self.root / "config" / "fabricproxy.yml").read_text(), "config")

    def test_minimotd_version_updated(self):
        self._apply()
        self.assertIn("V4.0.3", self.minimotd.read_text())
        self.assertNotIn("V3.9.21", self.minimotd.read_text())

    def test_maintenance_enabled_then_disabled_on_success(self):
        maint = VelocityMaintenanceToggle(self.maint_cfg)
        crafty = fake_crafty(players=0)
        live_apply_archive(
            archive_path=self.archive,
            root=self.root,
            staging_root=self.staging,
            backup_root=self.backup_root,
            crafty=crafty,
            maintenance=maint,
            minimotd_conf=self.minimotd,
            candidate_version="4.0.3",
            overlay_dir_name="Dontdeleteimportantmods",
        )
        self.assertFalse(maint.is_enabled(), "maintenance should be OFF after successful apply")

    def test_maintenance_left_on_if_health_fails(self):
        crafty = fake_crafty(players=0)
        crafty.wait_for_running.side_effect = RuntimeError("timeout waiting for server")
        maint = VelocityMaintenanceToggle(self.maint_cfg)
        with self.assertRaises(RuntimeError):
            live_apply_archive(
                archive_path=self.archive,
                root=self.root,
                staging_root=self.staging,
                backup_root=self.backup_root,
                crafty=crafty,
                maintenance=maint,
                minimotd_conf=self.minimotd,
                candidate_version="4.0.3",
                overlay_dir_name="Dontdeleteimportantmods",
            )
        self.assertTrue(maint.is_enabled(), "maintenance must stay ON after health failure")

    def test_backup_created_with_rollback_manifest(self):
        self._apply()
        backups = list(self.backup_root.glob("backup-*"))
        self.assertEqual(len(backups), 1)
        manifest = json.loads((backups[0] / "rollback-manifest.json").read_text())
        self.assertIn("entries", manifest)

    def test_player_gate_refuses_apply_when_players_online(self):
        with self.assertRaisesRegex(RuntimeError, "player"):
            self._apply(players=2)

    def test_force_bypasses_player_gate(self):
        result = self._apply(force=True, players=3)
        self.assertTrue(result.success)

    def test_rejected_archive_never_applied(self):
        # Archive with path traversal must be refused
        bad_archive = Path(self.tmp.name) / "bad.zip"
        bad_archive.write_bytes(make_zip({"../evil.sh": "bad", "mods/ok.jar": "fine"}))
        crafty = fake_crafty()
        maint = VelocityMaintenanceToggle(self.maint_cfg)
        with self.assertRaises((UnsafeArchiveError, RuntimeError)):
            live_apply_archive(
                archive_path=bad_archive,
                root=self.root,
                staging_root=self.staging,
                backup_root=self.backup_root,
                crafty=crafty,
                maintenance=maint,
                minimotd_conf=self.minimotd,
                candidate_version="0.0.1",
                overlay_dir_name="Dontdeleteimportantmods",
            )


class ApplyEndpointTests(unittest.TestCase):
    """HTTP-level tests for /apply and /force endpoints."""

    def setUp(self):
        import http.client
        import threading
        from http.server import ThreadingHTTPServer
        from app import make_handler

        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = base / "server"; self.root.mkdir()
        (self.root / "mods").mkdir()
        (self.root / "mods" / "Prominent-GLOBAL-MC1.20.1-4.0.2.jar").write_text("old")
        self.config = base / "config.json"
        self.staging = base / "staging"
        self.backup_root = base / "backups"
        self.maint_cfg = base / "maintenance.yml"
        self.maint_cfg.write_text("maintenance-enabled: false\n")
        self.minimotd = base / "main.conf"
        self.minimotd.write_text('motds=[{line2="V4.0.2"}]\n')
        # Pre-upload a candidate
        uploads = self.staging / "uploads"; uploads.mkdir(parents=True)
        self.archive = uploads / "Prominence-II-4.0.3.zip"
        self.archive.write_bytes(make_zip({"mods/new.jar": "new"}))
        self.config.write_text(json.dumps({
            "candidate_version": "4.0.3",
            "candidate_archive": "Prominence-II-4.0.3.zip",
            "protected_paths": ["server.properties", "fabric.jar", "world/"],
        }))

        # Fake Crafty
        self.mock_crafty = fake_crafty(players=0)

        with patch("app.CraftyControl", return_value=self.mock_crafty), \
             patch("app._read_crafty_token", return_value="fake-token"):
            handler = make_handler(
                root=self.root,
                config=self.config,
                staging=self.staging,
                backup_root=self.backup_root,
                velocity_maintenance_config=self.maint_cfg,
                minimotd_conf=self.minimotd,
                overlay_dir_name="Dontdeleteimportantmods",
            )
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.thread.join()
        self.httpd.server_close()
        self.tmp.cleanup()

    def request(self, method, path, body=b"", headers=None):
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.httpd.server_port)
        conn.request(method, path, body, headers or {})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data

    def test_apply_wrong_confirmation_rejected(self):
        body = b"confirm=APPLY+wrong"
        status, _ = self.request("POST", "/apply", body, {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, 400)

    def test_force_wrong_confirmation_rejected(self):
        body = b"confirm=FORCE+UPDATE+wrong"
        status, _ = self.request("POST", "/force", body, {"Content-Type": "application/x-www-form-urlencoded"})
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
