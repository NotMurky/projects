import io
import unittest
import zipfile

from updater_core import inspect_zip


class ZipInspectionTests(unittest.TestCase):
    def test_rejects_symlink_and_preserves_custom_content(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("mods/new.jar", b"new")
            archive.writestr("importantmods/yettwo.jar", b"custom")
            archive.writestr("server.properties", b"motd=x")
            link = zipfile.ZipInfo("mods/bad-link")
            link.external_attr = 0o120777 << 16
            archive.writestr(link, "target")
        report = inspect_zip(data.getvalue())
        self.assertEqual(report.install, ["mods/new.jar"])
        self.assertEqual(report.excluded, ["importantmods/yettwo.jar", "server.properties"])
        self.assertEqual(report.rejected, ["mods/bad-link"])


if __name__ == "__main__":
    unittest.main()
