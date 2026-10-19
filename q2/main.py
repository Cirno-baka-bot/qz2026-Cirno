import json
from pathlib import Path

UserRecord = dict[str, int | str]


class UserManager:
    """在内存中管理用户，并支持 JSON 文件持久化。"""

    def __init__(self) -> None:
        self.users: list[UserRecord] = []
        self.next_id: int = 1

    def add_user(self, name: str, age: int) -> UserRecord:
        """添加用户，分配当前编号后返回用户字典。"""
        user: UserRecord = {
            "id": self.next_id,
            "name": name,
            "age": age,
        }
        self.users.append(user)
        self.next_id += 1
        return user

    def get_user(self, user_id: int) -> UserRecord | None:
        """按 id 查找用户；找不到时返回 None。"""
        for user in self.users:
            if user["id"] == user_id:
                return user
        return None

    def update_age(self, user_id: int, new_age: int) -> bool:
        """修改用户年龄，成功返回 True，找不到用户返回 False。"""
        user = self.get_user(user_id)
        if user is None:
            return False
        user["age"] = new_age
        return True

    def remove_user(self, user_id: int) -> bool:
        """删除指定用户，成功返回 True，找不到用户返回 False。"""
        for index, user in enumerate(self.users):
            if user["id"] == user_id:
                del self.users[index]
                return True
        return False

    def list_users(self) -> list[UserRecord]:
        """按添加顺序返回用户列表的副本。"""
        return [user.copy() for user in self.users]

    def save_to_json(self, filepath: str) -> None:
        """使用 UTF-8 将当前用户列表保存为 JSON。"""
        path = Path(filepath)
        with path.open("w", encoding="utf-8") as file:
            json.dump(self.users, file, ensure_ascii=False, indent=2)

    def load_from_json(self, filepath: str) -> None:
        """从 JSON 文件加载用户，并接续最大 id。"""
        path = Path(filepath)
        with path.open("r", encoding="utf-8") as file:
            loaded_users: list[UserRecord] = json.load(file)

        self.users = loaded_users
        largest_id = max(
            (user["id"] for user in self.users),
            default=0,
        )
        self.next_id = largest_id + 1


if __name__ == "__main__":
    manager = UserManager()
    manager.add_user("张三", 18)
    manager.add_user("李四", 20)
    manager.update_age(1, 19)
    print(manager.list_users())
