import os
import tempfile
import unittest

from peko.core import pet_bond


class PetBondTests(unittest.TestCase):
    def test_record_increments_and_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "data", "pet_bond.json")
            self.assertEqual(pet_bond.record_completion("todo", path=path), 1)
            self.assertEqual(pet_bond.record_completion("habit", path=path), 2)
            self.assertEqual(pet_bond.record_completion("todo", path=path), 3)
            self.assertEqual(pet_bond.get_total(path=path), 3)
            self.assertEqual(pet_bond.get_by_kind(path=path), {"todo": 2, "habit": 1})

    def test_empty_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "data", "pet_bond.json")
            self.assertEqual(pet_bond.get_total(path=path), 0)
            self.assertEqual(pet_bond.get_by_kind(path=path), {})

    def test_corrupt_file_recovers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "data", "pet_bond.json")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write("{ not json")
            self.assertEqual(pet_bond.get_total(path=path), 0)
            self.assertEqual(pet_bond.record_completion("focus", path=path), 1)


if __name__ == "__main__":
    unittest.main()
