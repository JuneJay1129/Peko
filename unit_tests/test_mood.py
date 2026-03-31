import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta

from peko.core.mood import (
    BASELINE_MOOD,
    MoodEngine,
    MoodSnapshot,
    MoodStore,
    apply_interaction,
    expand_action_pool_by_mood,
    refresh_snapshot,
)


class MoodLogicTests(unittest.TestCase):
    def test_passive_decay_moves_toward_baseline(self):
        start = datetime(2026, 3, 20, 9, 0, 0)
        snapshot = MoodSnapshot(
            pet_id="hamster",
            mood_score=90,
            updated_at=start.isoformat(timespec="seconds"),
            daily_date=start.date().isoformat(),
        )
        refreshed = refresh_snapshot(snapshot, now=start + timedelta(hours=2))
        self.assertLess(refreshed.mood_score, 90)
        self.assertGreaterEqual(refreshed.mood_score, BASELINE_MOOD)

    def test_interaction_updates_score_counts_and_state(self):
        start = datetime(2026, 3, 20, 10, 0, 0)
        snapshot = MoodSnapshot(
            pet_id="hamster",
            mood_score=50,
            updated_at=start.isoformat(timespec="seconds"),
            daily_date=start.date().isoformat(),
        )
        outcome = apply_interaction(snapshot, "play", ["stand", "fight"], now=start)
        self.assertEqual(outcome.suggested_state, "fight")
        self.assertGreater(outcome.snapshot.mood_score, 50)
        self.assertEqual(outcome.snapshot.interaction_counts["play"], 1)
        self.assertEqual(outcome.snapshot.daily_interactions, 1)
        self.assertEqual(outcome.snapshot.last_interaction, "play")

    def test_repeat_interaction_has_diminishing_return(self):
        start = datetime(2026, 3, 20, 10, 0, 0)
        snapshot = MoodSnapshot(
            pet_id="hamster",
            mood_score=40,
            updated_at=start.isoformat(timespec="seconds"),
            daily_date=start.date().isoformat(),
        )
        first = apply_interaction(snapshot, "pet", ["stand"], now=start)
        second = apply_interaction(first.snapshot, "pet", ["stand"], now=start + timedelta(minutes=1))
        self.assertGreater(first.snapshot.mood_score - snapshot.mood_score, second.snapshot.mood_score - first.snapshot.mood_score)

    def test_auto_action_pool_is_weighted_by_mood(self):
        start = datetime(2026, 3, 20, 10, 0, 0)
        snapshot = MoodSnapshot(
            pet_id="hamster",
            mood_score=20,
            updated_at=start.isoformat(timespec="seconds"),
            daily_date=start.date().isoformat(),
        )
        weighted = expand_action_pool_by_mood(snapshot, ["stand", "sleep", "wave"])
        self.assertGreater(weighted.count("sleep"), weighted.count("wave"))


class MoodStoreTests(unittest.TestCase):
    def test_store_round_trip_and_bad_json_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "mood_state.json")
            store = MoodStore(path=path)
            now = datetime.now().replace(microsecond=0)
            snapshot = MoodSnapshot(
                pet_id="hamster",
                mood_score=66,
                updated_at=now.isoformat(timespec="seconds"),
                daily_date=now.date().isoformat(),
                daily_interactions=2,
            )
            store.save(snapshot)
            loaded = store.load("hamster", now=now + timedelta(minutes=5))
            self.assertEqual(loaded.pet_id, "hamster")
            self.assertEqual(loaded.daily_interactions, 2)

            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{ broken json")
            fallback = store.load("hamster", now=now + timedelta(minutes=5))
            self.assertEqual(fallback.mood_score, BASELINE_MOOD)

    def test_engine_persists_interaction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "mood_state.json")
            engine = MoodEngine("hamster", store=MoodStore(path=path))
            outcome = engine.apply_interaction("praise", ["stand", "wave"])
            self.assertIn(outcome.suggested_state, {"stand", "wave"})

            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            self.assertIn("hamster", payload["pets"])
            self.assertEqual(payload["pets"]["hamster"]["last_interaction"], "praise")


if __name__ == "__main__":
    unittest.main()
