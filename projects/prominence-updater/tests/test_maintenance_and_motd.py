"""Tests for VelocityMaintenanceToggle and update_minimotd_version."""
import os
import tempfile
import unittest
from pathlib import Path

from updater_core import VelocityMaintenanceToggle, update_minimotd_version


MAINTENANCE_YML = """\
language: en

maintenance-enabled: false

proxied-maintenance-servers:
- prom-survival
"""

MINIMOTD_CONF = """\
motds=[
    {
        icon=chest
        line1="<yellow>The Server"
        line2="<b>     <dark_red>Modded </dark_red>| <green>V3.9.21 </green>  </b>"
    }
]
"""


class VelocityMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "config.yml"
        self.cfg.write_text(MAINTENANCE_YML)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_maintenance_disabled(self):
        t = VelocityMaintenanceToggle(self.cfg)
        self.assertFalse(t.is_enabled())

    def test_enable_sets_true(self):
        t = VelocityMaintenanceToggle(self.cfg)
        t.enable()
        self.assertIn("maintenance-enabled: true", self.cfg.read_text())
        self.assertTrue(t.is_enabled())

    def test_disable_sets_false(self):
        t = VelocityMaintenanceToggle(self.cfg)
        t.enable()
        t.disable()
        self.assertIn("maintenance-enabled: false", self.cfg.read_text())
        self.assertFalse(t.is_enabled())

    def test_toggle_is_atomic_tmp_swap(self):
        # If tmp exists after enable, the swap succeeded.
        t = VelocityMaintenanceToggle(self.cfg)
        t.enable()
        # tmp must be gone (os.replace is atomic)
        tmp = self.cfg.with_suffix(".tmp")
        self.assertFalse(tmp.exists())

    def test_missing_key_raises(self):
        self.cfg.write_text("language: en\n")
        t = VelocityMaintenanceToggle(self.cfg)
        with self.assertRaises(OSError):
            t.enable()


class MiniMotdVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conf = Path(self.tmp.name) / "main.conf"
        self.conf.write_text(MINIMOTD_CONF)

    def tearDown(self):
        self.tmp.cleanup()

    def test_updates_version_in_line2(self):
        update_minimotd_version(self.conf, "4.0.3")
        self.assertIn("V4.0.3", self.conf.read_text())
        self.assertNotIn("V3.9.21", self.conf.read_text())

    def test_supports_hf_suffix(self):
        update_minimotd_version(self.conf, "4.0.3hf")
        self.assertIn("V4.0.3hf", self.conf.read_text())

    def test_no_version_does_not_corrupt_file(self):
        conf = Path(self.tmp.name) / "noversion.conf"
        conf.write_text('line2="<b>Modded Server</b>"\n')
        update_minimotd_version(conf, "4.0.3")
        # Falls back to inserting after Modded
        self.assertIn("4.0.3", conf.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
