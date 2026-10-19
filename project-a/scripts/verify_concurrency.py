# 用临时数据库验证并发浏览量。

import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def main() -> None:
    project_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(project_dir))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    from django.conf import settings

    with tempfile.TemporaryDirectory() as directory:
        settings.DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": str(Path(directory) / "concurrency.sqlite3"),
                "OPTIONS": {"timeout": 20},
            }
        }
        settings.ALLOWED_HOSTS = ["testserver"]
        settings.MEDIA_ROOT = str(Path(directory) / "media")
        import django

        django.setup()
        from django.contrib.auth import get_user_model
        from django.core.management import call_command
        from django.db import connection, connections
        from django.test import Client
        from django.urls import reverse

        from articles.models import Article

        call_command("migrate", verbosity=0, interactive=False)
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode=WAL")
        owner = get_user_model().objects.create_user(username="concurrency")
        article = Article.objects.create(title="并发计数", content="正文", author=owner)
        url = reverse("articles:detail", args=[article.pk])
        clients: list[Client] = []
        for _ in range(24):
            client = Client()
            client.force_login(owner)
            clients.append(client)

        def visit(client: Client) -> int:
            try:
                return client.get(url).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=4) as executor:
            statuses = list(executor.map(visit, clients))
        if statuses != [200] * 24:
            raise AssertionError(f"访问失败：{statuses}")
        article.refresh_from_db()
        if article.views != 24:
            raise AssertionError(f"浏览量丢失：期望 24，实际 {article.views}")
        if article.audit_logs.count() != 1:
            raise AssertionError("浏览量更新不应生成内容审计日志")
        print("PASS：4 个工作线程、24 次独立访问，浏览量准确为 24，只有创建日志。")
        connections.close_all()


if __name__ == "__main__":
    main()
