import unittest

from damage_discord import build_rcon_command, validate_minutes, validate_player


class DamageDiscordTests(unittest.TestCase):
    def test_builds_leaderboard_command(self):
        self.assertEqual(build_rcon_command(30, None), "damage 30")

    def test_builds_target_player_command(self):
        self.assertEqual(build_rcon_command(30, "_Murkyy_"), "damage 30 _Murkyy_")

    def test_minutes_must_be_positive(self):
        with self.assertRaises(ValueError):
            validate_minutes(0)

    def test_minutes_support_lifetime_scale_windows(self):
        self.assertEqual(validate_minutes(10_000_000), 10_000_000)

    def test_player_name_validation(self):
        self.assertEqual(validate_player("_Murkyy_"), "_Murkyy_")
        with self.assertRaises(ValueError):
            validate_player("bad name")


if __name__ == "__main__":
    unittest.main()
