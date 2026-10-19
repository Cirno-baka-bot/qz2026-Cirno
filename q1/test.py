import json
import tempfile
import unittest
from pathlib import Path

from main import analyze_log


class AnalyzeLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "app.jsonl"

    def write_lines(self, lines: list[str]) -> None:
        self.path.write_text("\n".join(lines), encoding="utf-8")

    def log_line(self, level: str, message: str, user: str) -> str:
        return json.dumps(
            {
                "timestamp": "2026-10-01 10:00:00",
                "level": level,
                "message": message,
                "user": user,
            },
            ensure_ascii=False,
        )

    def assert_empty_result(self) -> None:
        self.assertEqual(
            analyze_log(str(self.path)),
            {
                "total": 0,
                "by_level": {},
                "by_user": {},
                "last_error": None,
            },
        )

    def test_normal_logs_count_and_keep_last_error(self) -> None:
        self.write_lines(
            [
                self.log_line("INFO", "登录", "baka"),
                self.log_line("ERROR", "连接失败", "baka9"),
                self.log_line("ERROR", "请求超时", "baka"),
                self.log_line("INFO", "完成", "fumo"),
            ]
        )
        self.assertEqual(
            analyze_log(str(self.path)),
            {
                "total": 4,
                "by_level": {"INFO": 2, "ERROR": 2},
                "by_user": {"baka": 2, "baka9": 1, "fumo": 1},
                "last_error": "请求超时",
            },
        )

    def test_missing_file_returns_empty_result(self) -> None:
        self.assert_empty_result()

    def test_empty_file_returns_empty_result(self) -> None:
        self.write_lines([])
        self.assert_empty_result()

    def test_bad_and_blank_lines_do_not_stop_later_logs(self) -> None:
        self.write_lines(
            [
                "这不是 JSON",
                self.log_line("INFO", "正常", "baka"),
                "",
                "{",
                self.log_line("ERROR", "后面的错误", "baka9"),
            ]
        )
        self.assertEqual(
            analyze_log(str(self.path)),
            {
                "total": 2,
                "by_level": {"INFO": 1, "ERROR": 1},
                "by_user": {"baka": 1, "baka9": 1},
                "last_error": "后面的错误",
            },
        )

    def test_all_bad_lines_return_empty_result(self) -> None:
        self.write_lines(["bad", "{", " "])
        self.assert_empty_result()

    def test_no_error_keeps_last_error_none(self) -> None:
        self.write_lines([self.log_line("INFO", "完成", "baka")])
        self.assertIsNone(analyze_log(str(self.path))["last_error"])

    def test_calls_do_not_share_previous_counts(self) -> None:
        self.write_lines([self.log_line("INFO", "完成", "baka")])
        first = analyze_log(str(self.path))
        first["by_level"]["INFO"] = 99
        self.assertEqual(analyze_log(str(self.path))["by_level"], {"INFO": 1})


if __name__ == "__main__":
    unittest.main()
