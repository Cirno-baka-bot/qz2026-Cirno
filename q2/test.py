import json
import tempfile
import unittest
from pathlib import Path

from main import UserManager


class UserManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "users.json"
        self.manager = UserManager()

    def test_add_get_update_remove_and_list(self) -> None:
        first = self.manager.add_user("张三", 18)
        second = self.manager.add_user("李四", 20)
        self.assertEqual(first, {"id": 1, "name": "张三", "age": 18})
        self.assertEqual(second["id"], 2)
        self.assertEqual(self.manager.get_user(1), first)
        self.assertIsNone(self.manager.get_user(99))
        self.assertTrue(self.manager.update_age(1, 19))
        self.assertFalse(self.manager.update_age(99, 30))
        self.assertEqual(self.manager.get_user(1)["age"], 19)
        self.assertTrue(self.manager.remove_user(2))
        self.assertFalse(self.manager.remove_user(2))
        self.assertEqual(
            self.manager.list_users(),
            [
                {"id": 1, "name": "张三", "age": 19},
            ],
        )

    def test_ids_continue_after_delete(self) -> None:
        self.manager.add_user("一", 1)
        self.manager.add_user("二", 2)
        self.manager.remove_user(1)
        self.assertEqual(self.manager.add_user("三", 3)["id"], 3)

    def test_list_users_returns_a_list_copy(self) -> None:
        self.manager.add_user("张三", 18)
        listed = self.manager.list_users()
        listed.clear()
        self.assertEqual(len(self.manager.list_users()), 1)

    def test_save_uses_utf8_and_preserves_chinese(self) -> None:
        self.manager.add_user("张三", 18)
        self.manager.save_to_json(str(self.path))
        text = self.path.read_text(encoding="utf-8")
        self.assertIn("张三", text)
        self.assertNotIn("\\u5f20", text)
        self.assertEqual(json.loads(text)[0]["name"], "张三")

    def test_load_overwrites_current_users_and_continues_max_id(self) -> None:
        self.manager.add_user("旧用户", 99)
        self.path.write_text(
            json.dumps(
                [
                    {"id": 2, "name": "张三", "age": 18},
                    {"id": 7, "name": "李四", "age": 20},
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.manager.load_from_json(str(self.path))
        self.assertEqual(
            self.manager.list_users(),
            [
                {"id": 2, "name": "张三", "age": 18},
                {"id": 7, "name": "李四", "age": 20},
            ],
        )
        self.assertEqual(self.manager.add_user("王五", 21)["id"], 8)

    def test_load_empty_list_resets_next_id(self) -> None:
        self.manager.add_user("旧用户", 99)
        self.path.write_text("[]", encoding="utf-8")
        self.manager.load_from_json(str(self.path))
        self.assertEqual(self.manager.add_user("新用户", 18)["id"], 1)

    def test_save_then_load_round_trip(self) -> None:
        self.manager.add_user("张三", 19)
        self.manager.add_user("李四", 20)
        self.manager.save_to_json(str(self.path))
        restored = UserManager()
        restored.load_from_json(str(self.path))
        self.assertEqual(restored.list_users(), self.manager.list_users())


if __name__ == "__main__":
    unittest.main()
