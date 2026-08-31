import unittest

from updater_core import build_update_plan


class UpdatePlanTests(unittest.TestCase):
    def test_preserves_builtin_and_user_protected_paths(self):
        archive_paths = [
            "mods/new-mod.jar",
            "importantmods/custom.jar",
            "fabric.jar",
            "server.properties",
            "config/new.json",
            "world/level.dat",
            "../escape",
        ]
        plan = build_update_plan(archive_paths, user_protected=["config/new.json"])

        self.assertEqual(plan.install, ["mods/new-mod.jar"])
        self.assertEqual(
            plan.excluded,
            [
                "importantmods/custom.jar",
                "fabric.jar",
                "server.properties",
                "config/new.json",
                "world/level.dat",
            ],
        )
        self.assertEqual(plan.rejected, ["../escape"])

    def test_user_protected_directory_excludes_children(self):
        plan = build_update_plan(
            ["mods/a.jar", "kubejs/config.js", "kubejs/assets/icon.png"],
            user_protected=["kubejs/"],
        )
        self.assertEqual(plan.install, ["mods/a.jar"])
        self.assertEqual(plan.excluded, ["kubejs/config.js", "kubejs/assets/icon.png"])


if __name__ == "__main__":
    unittest.main()
