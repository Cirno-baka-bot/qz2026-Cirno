from django.apps import AppConfig


class ArticlesConfig(AppConfig):
    name = "articles"

    def ready(self) -> None:
        from . import signals  # noqa: F401 — 导入时登记接收函数。
