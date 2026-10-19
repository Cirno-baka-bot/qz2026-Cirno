from django.conf import settings
from django.db import models

# Create your models here.


class Article(models.Model):
    # 仅用于当前操作的 Python 属性，不增加数据库字段。
    _audit_actor_id: int | None = None
    _audit_changes: dict[str, dict[str, str | None]]

    title = models.CharField(max_length=300)
    content = models.TextField("正文")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        verbose_name="作者",
    )

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHED = "published", "已发布"
        ARCHIVED = "archived", "已归档"

    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    views = models.PositiveIntegerField("浏览量", default=0)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)
    updated_at = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "文章"
        verbose_name_plural = "文章"

    def __str__(self) -> str:
        return self.title


class Attachment(models.Model):
    filename = models.CharField("文件名", max_length=255)
    file = models.FileField("文件", upload_to="attachments/")
    article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="所属文章",
    )
    uploaded_at = models.DateTimeField("上传时间", auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at", "-pk"]
        verbose_name = "附件"
        verbose_name_plural = "附件"

    def __str__(self) -> str:
        return self.filename


class AuditLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "创建"
        UPDATE = "update", "修改"
        PUBLISH = "publish", "发布"
        ARCHIVE = "archive", "归档"
        DELETE = "delete", "删除"

    action = models.CharField(
        "操作",
        max_length=20,
        choices=Action.choices,
    )

    article = models.ForeignKey(
        Article,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        verbose_name="文章",
    )

    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="article_audit_logs",
        verbose_name="操作人",
    )

    created_at = models.DateTimeField(
        "操作时间",
        auto_now_add=True,
    )

    changes = models.JSONField(
        "变化摘要",
        default=dict,
    )

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "审计日志"
        verbose_name_plural = "审计日志"

    def __str__(self) -> str:
        return f"{self.get_action_display()} #{self.pk}"
