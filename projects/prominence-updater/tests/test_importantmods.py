import unittest

from updater_core import importantmods_overlay_plan


class ImportantModsOverlayTests(unittest.TestCase):
    def test_reapplies_all_files_except_world_data(self):
        """Any file in the overlay dir is restored, except live world directories."""
        plan = importantmods_overlay_plan([
            "mods/yettwo.jar", "config/fabricproxy.yml", "world/level.dat",
            "worldnopregen/region/r.0.0.mca", "notes.txt",
        ])
        self.assertIn("mods/yettwo.jar", plan)
        self.assertIn("config/fabricproxy.yml", plan)
        self.assertIn("notes.txt", plan)
        # World data must never be overlaid — it is live server state
        self.assertNotIn("world/level.dat", plan)
        self.assertNotIn("worldnopregen/region/r.0.0.mca", plan)

    def test_rejects_unsafe_paths(self):
        plan = importantmods_overlay_plan(["../escape", "\x00evil"])
        self.assertEqual(plan, [])


if __name__ == "__main__":
    unittest.main()
