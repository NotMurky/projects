import os
import sqlite3
import tempfile
import unittest

import boss_watch


def make_db(path):
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE boss_sessions(boss_entity_uuid TEXT PRIMARY KEY, boss_type_id TEXT, boss_display_name TEXT,
            spawned_at INTEGER, spawn_dimension TEXT, spawn_position TEXT, ended_at INTEGER, end_reason TEXT);
        CREATE TABLE raw_hits(id INTEGER PRIMARY KEY AUTOINCREMENT, occurred_at INTEGER, attacker_uuid TEXT,
            attacker_name TEXT, attribution_kind TEXT, untraceable_source_name TEXT, target_uuid TEXT,
            target_player_name TEXT, target_type_id TEXT, target_category TEXT, dimension TEXT,
            actual_damage REAL, boss_session_uuid TEXT, damage_source_name TEXT);
        """
    )
    con.commit()
    return con


class BossWatchTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.db = os.path.join(self.dir, "damage.db")
        self.con = make_db(self.db)

    def test_hearts_formatting(self):
        self.assertEqual(boss_watch.hearts(5.0), "2.5 hearts")
        self.assertEqual(boss_watch.hearts(10.0), "5 hearts")
        self.assertEqual(boss_watch.hearts(2.0), "1 heart")
        self.assertEqual(boss_watch.hearts(10000.0), "5,000 hearts")

    def test_new_spawns_respects_cursor(self):
        self.con.execute("INSERT INTO boss_sessions VALUES('u1','minecraft:wither','Wither',1000,'d','0,0,0',NULL,NULL)")
        self.con.execute("INSERT INTO boss_sessions VALUES('u2','minecraft:warden','Warden',2000,'d','0,0,0',NULL,NULL)")
        self.con.commit()
        rows = boss_watch.new_spawns(self.db, 1500)
        self.assertEqual([r[0] for r in rows], ["u2"])

    def test_new_deaths_only_death_reason(self):
        self.con.execute("INSERT INTO boss_sessions VALUES('u1','x','Boss A',1000,'d','0,0,0',3000,'death')")
        self.con.execute("INSERT INTO boss_sessions VALUES('u2','x','Boss B',1000,'d','0,0,0',3500,'despawn')")
        self.con.commit()
        rows = boss_watch.new_deaths(self.db, 0)
        self.assertEqual([r[0] for r in rows], ["u1"])

    def test_session_summary_total_contribs_unattributed(self):
        self.con.execute("INSERT INTO boss_sessions VALUES('b','x','Boss',1000,'d','0,0,0',9000,'death')")
        rows = [
            ("pa", "Alice", 20.0),
            ("pa", "Alice", 10.0),
            ("pb", "Bob", 8.0),
            (None, None, 4.0),
        ]
        for uuid, name, dmg in rows:
            self.con.execute(
                "INSERT INTO raw_hits(occurred_at,attacker_uuid,attacker_name,attribution_kind,target_uuid,target_type_id,target_category,dimension,actual_damage,boss_session_uuid,damage_source_name) VALUES(1,?,?,?,?,?,?,?,?,?,?)",
                (uuid, name, "DIRECT" if uuid else "UNTRACEABLE", "t", "minecraft:zombie", "ENTITY", "d", dmg, "b", "x"),
            )
        self.con.commit()
        total, contribs, unattr = boss_watch.session_summary(self.db, "b")
        self.assertAlmostEqual(total, 42.0)
        self.assertEqual(contribs[0], ("Alice", 30.0))
        self.assertEqual(contribs[1], ("Bob", 8.0))
        self.assertAlmostEqual(unattr, 4.0)

    def test_render_death_hides_unattributed_when_zero(self):
        msg = boss_watch.render_death("Wither", 100.0, [("Alice", 60.0), ("Bob", 40.0)], 0.0)
        self.assertIn("Wither", msg)
        self.assertIn("50 hearts", msg)  # Alice 60hp = 30 hearts... total 100hp=50 hearts
        self.assertNotIn("naccounted", msg)
        self.assertNotIn("nattributed", msg)

    def test_render_death_shows_unattributed_when_present(self):
        msg = boss_watch.render_death("Wither", 100.0, [("Alice", 80.0)], 20.0)
        self.assertIn("nattributed", msg.lower())


if __name__ == "__main__":
    unittest.main()
