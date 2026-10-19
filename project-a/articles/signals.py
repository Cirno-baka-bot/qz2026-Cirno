from functools import partial

from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver

from .models import Article, Attachment, AuditLog


@receiver(pre_save, sender=Article, dispatch_uid="articles.collect_changes")
def collect_article_changes(
    sender: type[Article],
    instance: Article,
    raw: bool,
    using: str,
    update_fields: frozenset[str] | None,
    **kwargs: object,
) -> None:
    """读取保存前的业务字段，只比较本次真正写入的字段。"""
    instance._audit_changes = {}
    if raw:
        return

    fields = ("title", "content", "status")
    old = sender.objects.using(using).filter(pk=instance.pk).values(*fields).first()
    for field in fields:
        if update_fields is not None and field not in update_fields:
            continue
        before = old[field] if old is not None else None
        after = getattr(instance, field)
        if before != after:
            instance._audit_changes[field] = {"old": before, "new": after}


@receiver(post_save, sender=Article, dispatch_uid="articles.record_saved")
def record_article_saved(
    sender: type[Article],
    instance: Article,
    created: bool,
    raw: bool,
    using: str,
    **kwargs: object,
) -> None:
    """根据业务变化写审计；浏览量和无变化保存不产生修改日志。"""
    if raw:
        return
    changes = instance._audit_changes
    if not created and not changes:
        return
    if created:
        action = AuditLog.Action.CREATE
    elif "status" in changes and instance.status == Article.Status.PUBLISHED:
        action = AuditLog.Action.PUBLISH
    elif "status" in changes and instance.status == Article.Status.ARCHIVED:
        action = AuditLog.Action.ARCHIVE
    else:
        action = AuditLog.Action.UPDATE
    AuditLog.objects.using(using).create(
        article=instance,
        operator_id=instance._audit_actor_id,
        action=action,
        changes=changes,
    )


@receiver(pre_delete, sender=Article, dispatch_uid="articles.record_deleted")
def record_article_deleted(
    sender: type[Article],
    instance: Article,
    using: str,
    **kwargs: object,
) -> None:
    """保留删除快照，删除日志不引用即将消失的文章。"""
    AuditLog.objects.using(using).create(
        article=None,
        operator_id=instance._audit_actor_id,
        action=AuditLog.Action.DELETE,
        changes={
            "id": {"old": str(instance.pk), "new": None},
            "title": {"old": instance.title, "new": None},
            "content": {"old": instance.content, "new": None},
            "status": {"old": instance.status, "new": None},
        },
    )


@receiver(post_delete, sender=Attachment, dispatch_uid="articles.remove_file")
def remove_attachment_file(
    sender: type[Attachment],
    instance: Attachment,
    using: str,
    **kwargs: object,
) -> None:
    """仅在数据库提交后删除文件，避免回滚后记录指向已删文件。"""
    if instance.file.name:
        transaction.on_commit(
            partial(instance.file.storage.delete, instance.file.name),
            using=using,
        )
