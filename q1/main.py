import json
from pathlib import Path


def analyze_log(filepath: str) -> dict:
    """逐行统计 JSON 日志，文件缺失返回空结果，坏行跳过。"""
    total: int = 0
    by_level: dict[str, int] = {}
    by_user: dict[str, int] = {}
    last_error: str | None = None

    try:
        with open(filepath, "r", encoding="utf-8") as file:
            for line in file:
                try:
                    log = json.loads(line)
                except json.JSONDecodeError:
                    # 只跳过当前坏行，后续日志仍继续处理。
                    continue

                total += 1

                level = log["level"]
                user = log["user"]

                by_level[level] = by_level.get(level, 0) + 1
                by_user[user] = by_user.get(user, 0) + 1

                if level == "ERROR":
                    last_error = log["message"]
    except FileNotFoundError:
        # 文件没打开，统计仍是初始空值，继续到下方统一返回。
        pass

    return {
        "total": total,
        "by_level": by_level,
        "by_user": by_user,
        "last_error": last_error,
    }


if __name__ == "__main__":
    filepath = Path(__file__).with_name("app.jsonl")
    result = analyze_log(str(filepath))
    print(result)
