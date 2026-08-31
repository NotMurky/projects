import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from updater_core import (
    ConfirmationRequired,
    CraftyPlayerGate,
    UnsafeArchiveError,
    create_backup_manifest,
    derive_candidate_version,
    inspect_zip,
    preflight_disk_space,
    require_force_confirmation,
    stage_archive,
    update_motd,
)


def make_zip(entries):
    blob = io.BytesIO()
    with zipfile.ZipFile(blob, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return blob.getvalue()


class SafetyWorkflowTests(unittest.TestCase):
    def test_immutable_paths_include_variables_and_all_world_variants(self):
        report = inspect_zip(make_zip({
            "variables.txt": "x", "world/level.dat": "x", "worldnopregen/a": "x",
            "mods/new.jar": "x",
        }))
        self.assertEqual(report.install, ["mods/new.jar"])
        self.assertEqual(report.excluded, ["variables.txt", "world/level.dat", "worldnopregen/a"])

    def test_rejects_duplicate_members_before_staging(self):
        blob = io.BytesIO()
        with zipfile.ZipFile(blob, "w") as archive:
            archive.writestr("mods/a.jar", b"first")
            archive.writestr("mods/a.jar", b"second")
        with self.assertRaises(UnsafeArchiveError):
            inspect_zip(blob.getvalue())

    def test_candidate_version_prefers_manifest_then_filename(self):
        self.assertEqual(derive_candidate_version("Prominence-II-v3.2.1.zip", None), "3.2.1")
        self.assertEqual(derive_candidate_version("anything.zip", "4.0.0hf"), "4.0.0hf")

    def test_force_needs_exact_candidate_confirmation(self):
        with self.assertRaises(ConfirmationRequired):
            require_force_confirmation("3.2.1", "FORCE UPDATE 3.2.0")
        self.assertTrue(require_force_confirmation("3.2.1", "FORCE UPDATE 3.2.1"))

    def test_preflight_reports_insufficient_space_without_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            report = preflight_disk_space(Path(temp), required_bytes=10**30)
        self.assertFalse(report.ok)
        self.assertGreater(report.required_bytes, report.available_bytes)

    def test_backup_manifest_copies_existing_target_and_records_missing_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "server"; root.mkdir()
            (root / "mods").mkdir(); (root / "mods" / "old.jar").write_text("old")
            backup = Path(temp) / "backup"
            manifest = create_backup_manifest(root, ["mods/old.jar", "config/missing.json"], backup)
            self.assertEqual(manifest["entries"][0]["status"], "copied")
            self.assertEqual(manifest["entries"][1]["status"], "missing")
            self.assertEqual((backup / "files" / "mods" / "old.jar").read_text(), "old")
            self.assertEqual(json.loads((backup / "rollback-manifest.json").read_text())["entries"], manifest["entries"])

    def test_staging_never_changes_server_and_overlays_custom_mods(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp); root = base / "server"; root.mkdir()
            (root / "mods").mkdir(); (root / "mods" / "live.jar").write_text("live")
            # Use the real overlay dir name
            overlay = root / "Dontdeleteimportantmods"
            (overlay / "mods").mkdir(parents=True)
            (overlay / "config").mkdir(parents=True)
            (overlay / "mods" / "custom.jar").write_text("custom")
            (overlay / "config" / "custom.json").write_text("custom")
            archive = base / "pack.zip"
            archive.write_bytes(make_zip({
                "mods/new.jar": "new", "config/pack.json": "pack", "server.properties": "bad",
            }))
            result = stage_archive(archive, root, base / "staging",
                                   overlay_dir_name="Dontdeleteimportantmods")
            self.assertEqual((root / "mods" / "live.jar").read_text(), "live")
            self.assertFalse((root / "mods" / "new.jar").exists())
            self.assertEqual((result.stage_dir / "mods" / "new.jar").read_text(), "new")
            self.assertEqual((result.stage_dir / "mods" / "custom.jar").read_text(), "custom")
            self.assertEqual((result.stage_dir / "config" / "custom.json").read_text(), "custom")
            self.assertFalse((result.stage_dir / "server.properties").exists())

    def test_update_motd_only_replaces_motd_line(self):
        with tempfile.TemporaryDirectory() as temp:
            props = Path(temp) / "server.properties"
            props.write_text("motd=old\nmax-players=10\n")
            update_motd(props, "3.2.1")
            self.assertEqual(props.read_text(), "motd=Prominence II Hasturian Era v3.2.1\nmax-players=10\n")

    def test_crafty_gate_uses_injected_read_only_transport(self):
        calls = []
        def transport(url, headers):
            calls.append((url, headers))
            return {"data": {"online": 2}}
        gate = CraftyPlayerGate("https://crafty.invalid", "server-id", "secret", transport=transport)
        self.assertEqual(gate.player_count(), 2)
        self.assertIn("/api/v2/servers/server-id/stats", calls[0][0])
        self.assertEqual(calls[0][1]["Authorization"], "Bearer secret")


if __name__ == "__main__":
    unittest.main()
