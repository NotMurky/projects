"""Unit tests for the hours tracker: parsers + AFK state machine + store."""
import os
import tempfile
import unittest

import tracker as T
from store import Store, fmt_hours


class ParseTests(unittest.TestCase):
    def test_list_multi(self):
        r = "There are 3 of a max of 20 players online: Alice, Bob, _Murkyy_"
        self.assertEqual(T.parse_list(r), ["Alice", "Bob", "_Murkyy_"])

    def test_list_empty(self):
        r = "There are 0 of a max of 20 players online: "
        self.assertEqual(T.parse_list(r), [])

    def test_pos(self):
        r = "Alice has the following entity data: [12.5d, 64.0d, -8.25d]"
        self.assertEqual(T.parse_vec(r), (12.5, 64.0, -8.25))

    def test_rotation(self):
        r = "Alice has the following entity data: [178.4f, -12.0f]"
        self.assertEqual(T.parse_vec(r), (178.4, -12.0))

    def test_no_such_player(self):
        r = "No entity was found"
        self.assertIsNone(T.parse_vec(r))


class MovedTests(unittest.TestCase):
    def test_still(self):
        self.assertFalse(T.Tracker._moved((1.0, 2.0, 3.0), (1.0, 2.0, 3.0), T.POS_EPSILON))

    def test_tiny_noise_ignored(self):
        self.assertFalse(T.Tracker._moved((1.0, 2.0, 3.0), (1.005, 2.0, 3.0), T.POS_EPSILON))

    def test_real_move(self):
        self.assertTrue(T.Tracker._moved((1.0, 2.0, 3.0), (1.5, 2.0, 3.0), T.POS_EPSILON))

    def test_unknown_is_active(self):
        self.assertTrue(T.Tracker._moved(None, (1.0, 2.0, 3.0), T.POS_EPSILON))


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        self.store = Store(self.tmp.name)

    def tearDown(self):
        self.store.close()
        os.unlink(self.tmp.name)

    def test_accumulate(self):
        self.store.add_time("Alice", active=100, afk=0)
        self.store.add_time("Alice", active=50, afk=20)
        row = self.store.get("Alice")
        self.assertEqual(row["active_seconds"], 150)
        self.assertEqual(row["afk_seconds"], 20)

    def test_case_insensitive_get(self):
        self.store.add_time("Alice", active=10)
        self.assertIsNotNone(self.store.get("alice"))

    def test_leaderboard_order(self):
        self.store.add_time("Low", active=10)
        self.store.add_time("High", active=999)
        lb = self.store.leaderboard(10)
        self.assertEqual(lb[0]["name"], "High")


class FmtTests(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual(fmt_hours(0), "0m")
        self.assertEqual(fmt_hours(90 * 60), "1h 30m")
        self.assertEqual(fmt_hours(3600), "1h")
        self.assertEqual(fmt_hours(45 * 60), "45m")


class AfkStateMachineTests(unittest.TestCase):
    """Drive Tracker.poll_once with a fake RCON to exercise the AFK flip."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.tmp.close()
        # Build a Tracker without touching real RCON/env.
        self.tr = T.Tracker.__new__(T.Tracker)
        self.tr.store = Store(self.tmp.name)
        self.tr.states = {}
        import threading
        self.tr._stop = threading.Event()
        self.scripted = {}  # name -> (pos, rot)
        self.online = ["Alice"]

        class FakeRcon:
            def __init__(self, outer):
                self.outer = outer
            def command(self, cmd):
                if cmd == "list":
                    names = ", ".join(self.outer.online)
                    n = len(self.outer.online)
                    return f"There are {n} of a max of 20 players online: {names}"
                if cmd.startswith("data get entity"):
                    parts = cmd.split()
                    name = parts[3]
                    which = parts[4]
                    pos, rot = self.outer.scripted[name]
                    vec = pos if which == "Pos" else rot
                    body = "[" + ", ".join(f"{v}d" for v in vec) + "]"
                    return f"{name} has the following entity data: {body}"
                return ""
            def close(self):
                pass

        self.tr.rcon = FakeRcon(self)

    def tearDown(self):
        self.tr.store.close()
        os.unlink(self.tmp.name)

    def test_standing_still_goes_afk_and_credits_afk_bucket(self):
        self.scripted["Alice"] = ((0.0, 64.0, 0.0), (0.0, 0.0))
        t = 1000.0
        # First poll: establishes state, credits nothing.
        self.tr.poll_once(t)
        # Advance in 60s steps, never moving. AFK_THRESHOLD default 300s.
        for _ in range(12):  # 12 * 60 = 720s total
            t += 60
            self.tr.poll_once(t)
        row = self.tr.store.get("Alice")
        # Idle the whole time: first 300s counts active (grace), rest AFK.
        self.assertGreater(row["afk_seconds"], 0)
        self.assertTrue(self.tr.states["Alice"].is_afk)
        # Active credited should be roughly the 5-min grace window (<= 360s).
        self.assertLessEqual(row["active_seconds"], 360)

    def test_movement_resets_and_keeps_active(self):
        self.scripted["Alice"] = ((0.0, 64.0, 0.0), (0.0, 0.0))
        t = 1000.0
        self.tr.poll_once(t)
        for i in range(12):
            t += 60
            # Move every poll: bump X.
            px = float(i + 1)
            self.scripted["Alice"] = ((px, 64.0, 0.0), (0.0, 0.0))
            self.tr.poll_once(t)
        row = self.tr.store.get("Alice")
        self.assertFalse(self.tr.states["Alice"].is_afk)
        self.assertEqual(row["afk_seconds"], 0)
        self.assertGreater(row["active_seconds"], 600)

    def test_look_around_counts_as_active(self):
        # Position frozen, only rotation changes -> still active.
        t = 1000.0
        self.scripted["Alice"] = ((0.0, 64.0, 0.0), (0.0, 0.0))
        self.tr.poll_once(t)
        for i in range(12):
            t += 60
            self.scripted["Alice"] = ((0.0, 64.0, 0.0), (float(i * 10), 0.0))
            self.tr.poll_once(t)
        self.assertFalse(self.tr.states["Alice"].is_afk)

    def test_leaving_clears_state(self):
        self.scripted["Alice"] = ((0.0, 64.0, 0.0), (0.0, 0.0))
        self.tr.poll_once(1000.0)
        self.assertIn("Alice", self.tr.states)
        self.online = []  # Alice logs off
        self.tr.poll_once(1060.0)
        self.assertNotIn("Alice", self.tr.states)


if __name__ == "__main__":
    unittest.main()
