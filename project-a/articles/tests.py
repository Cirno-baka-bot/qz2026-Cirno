import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase, override_settings

from .models import Article, Attachment, AuditLog


class AuditTests(TestCase):
    def setUp(self) -> None:
        self.author = get_user_model().objects.create_user(username="author")
        self.operator = get_user_model().objects.create_user(username="operator")
        self.article = Article(
            title="原始标题",
            content="原始正文",
            author=self.author,
        )
        self.article._audit_actor_id = self.operator.pk
        self.article.save()

    def test_creation_records_snapshot_and_actual_operator(self) -> None:
        log = self.article.audit_logs.get()
        self.assertEqual(log.action, AuditLog.Action.CREATE)
        self.assertEqual(log.operator, self.operator)
        self.assertEqual(log.changes["title"], {"old": None, "new": "原始标题"})
        self.assertEqual(log.changes["status"], {"old": None, "new": "draft"})

    def test_unknown_operator_is_not_assumed_to_be_author(self) -> None:
        article = Article.objects.create(
            title="系统创建",
            content="正文",
            author=self.author,
        )
        self.assertIsNone(article.audit_logs.get().operator_id)

    def test_title_and_content_edit_records_old_and_new_values(self) -> None:
        self.article.title = "修改标题"
        self.article.content = "修改正文"
        self.article.save()
        log = self.article.audit_logs.first()
        self.assertEqual(log.action, AuditLog.Action.UPDATE)
        self.assertEqual(
            log.changes,
            {
                "title": {"old": "原始标题", "new": "修改标题"},
                "content": {"old": "原始正文", "new": "修改正文"},
            },
        )

    def test_status_transitions_choose_correct_action(self) -> None:
        for status, action in (
            (Article.Status.PUBLISHED, AuditLog.Action.PUBLISH),
            (Article.Status.ARCHIVED, AuditLog.Action.ARCHIVE),
            (Article.Status.DRAFT, AuditLog.Action.UPDATE),
        ):
            with self.subTest(status=status):
                previous = self.article.status
                self.article.status = status
                self.article.save(update_fields=["status", "updated_at"])
                log = self.article.audit_logs.first()
                self.assertEqual(log.action, action)
                self.assertEqual(
                    log.changes,
                    {
                        "status": {"old": previous, "new": status},
                    },
                )

    def test_unchanged_save_does_not_add_log(self) -> None:
        self.article.save()
        self.assertEqual(self.article.audit_logs.count(), 1)

    def test_only_persisted_fields_are_audited(self) -> None:
        self.article.title = "仅保存标题"
        self.article.content = "此正文没有保存"
        self.article.save(update_fields=["title"])
        self.assertEqual(
            self.article.audit_logs.first().changes,
            {
                "title": {"old": "原始标题", "new": "仅保存标题"},
            },
        )
        self.article.refresh_from_db()
        self.assertEqual(self.article.content, "原始正文")

    def test_views_only_save_is_not_a_content_edit(self) -> None:
        self.article.views = 3
        self.article.save(update_fields=["views"])
        self.assertEqual(self.article.audit_logs.count(), 1)

    def test_raw_save_skips_audit(self) -> None:
        self.article.title = "导入标题"
        self.article.save_base(raw=True)
        self.assertEqual(self.article.audit_logs.count(), 1)

    def test_delete_keeps_logs_and_identifying_snapshot(self) -> None:
        pk = self.article.pk
        self.article.delete()
        self.assertFalse(Article.objects.filter(pk=pk).exists())
        self.assertEqual(AuditLog.objects.count(), 2)
        self.assertFalse(AuditLog.objects.filter(article__isnull=False).exists())
        log = AuditLog.objects.get(action=AuditLog.Action.DELETE)
        self.assertEqual(log.operator_id, self.operator.pk)
        self.assertEqual(log.changes["id"], {"old": str(pk), "new": None})
        self.assertEqual(log.changes["title"]["old"], "原始标题")

    def test_queryset_delete_also_records_deletion(self) -> None:
        Article.objects.filter(pk=self.article.pk).delete()
        self.assertEqual(AuditLog.objects.filter(action="delete").count(), 1)

    def test_deleted_operator_does_not_destroy_audit(self) -> None:
        self.operator.delete()
        self.assertIsNone(self.article.audit_logs.get().operator_id)

    def test_outer_transaction_rollback_rolls_back_article_and_log(self) -> None:
        with self.assertRaisesMessage(ValueError, "取消"):
            with transaction.atomic():
                Article.objects.create(
                    title="不保留", content="正文", author=self.author
                )
                raise ValueError("取消")
        self.assertEqual(Article.objects.count(), 1)
        self.assertEqual(AuditLog.objects.count(), 1)


class AttachmentStorageTests(TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.media_settings = override_settings(MEDIA_ROOT=self.directory.name)
        self.media_settings.enable()
        self.addCleanup(self.media_settings.disable)
        self.user = get_user_model().objects.create_user(username="owner")
        self.article = Article.objects.create(
            title="附件文章",
            content="正文",
            author=self.user,
        )
        self.attachment = Attachment.objects.create(
            filename="说明.txt",
            article=self.article,
            file=SimpleUploadedFile("readme.txt", b"attachment"),
        )
        self.path = Path(self.attachment.file.path)

    def test_deleted_attachment_removes_file_after_commit(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.attachment.delete()
            self.assertTrue(self.path.exists())
        self.assertFalse(self.path.exists())

    def test_deleting_article_also_cleans_up_attachments(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.article.delete()
        self.assertFalse(Attachment.objects.exists())
        self.assertFalse(self.path.exists())

    def test_rolled_back_delete_keeps_record_and_file(self) -> None:
        pk = self.attachment.pk
        with self.captureOnCommitCallbacks(execute=True):
            with self.assertRaisesMessage(ValueError, "取消"):
                with transaction.atomic():
                    self.attachment.delete()
                    raise ValueError("取消")
        self.assertTrue(Attachment.objects.filter(pk=pk).exists())
        self.assertTrue(self.path.exists())


class ArticlePageTests(TestCase):
    def setUp(self) -> None:
        from django.urls import reverse

        self.reverse = reverse
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        media_settings = override_settings(MEDIA_ROOT=self.directory.name)
        media_settings.enable()
        self.addCleanup(media_settings.disable)
        self.owner = get_user_model().objects.create_user(username="owner")
        self.other = get_user_model().objects.create_user(username="other")
        self.article = Article.objects.create(
            title="网页测试文章",
            content="正文",
            author=self.owner,
        )
        self.detail_url = reverse("articles:detail", args=[self.article.pk])
        self.edit_url = reverse("articles:edit", args=[self.article.pk])
        self.delete_url = reverse("articles:delete", args=[self.article.pk])
        self.upload_url = reverse("articles:upload", args=[self.article.pk])
        self.client.force_login(self.owner)

    def test_anonymous_read_and_write_redirect_to_login(self) -> None:
        self.client.logout()
        for url in (self.reverse("articles:list"), self.detail_url, self.edit_url):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 302)
                self.assertIn(self.reverse("login"), response.url)
        response = self.client.post(self.upload_url)
        self.assertEqual(response.status_code, 302)

    def test_create_assigns_logged_in_author_and_operator(self) -> None:
        response = self.client.post(
            self.reverse("articles:create"),
            {
                "title": "新文章",
                "content": "新正文",
                "status": "draft",
                "author": self.other.pk,
                "views": 999,
            },
        )
        article = Article.objects.get(title="新文章")
        self.assertRedirects(
            response,
            self.reverse("articles:detail", args=[article.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(article.author, self.owner)
        self.assertEqual(article.views, 0)
        self.assertEqual(article.audit_logs.get().operator_id, self.owner.pk)

    def test_invalid_create_does_not_save_article_or_log(self) -> None:
        before = AuditLog.objects.count()
        response = self.client.post(
            self.reverse("articles:create"),
            {
                "title": "",
                "content": "正文",
                "status": "invalid",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(Article.objects.count(), 1)
        self.assertEqual(AuditLog.objects.count(), before)

    def test_detail_increments_views_and_shows_audit_without_new_log(self) -> None:
        for expected in (1, 2):
            response = self.client.get(self.detail_url)
            self.assertContains(response, "网页测试文章")
            self.assertContains(response, "操作记录")
            self.article.refresh_from_db()
            self.assertEqual(self.article.views, expected)
        self.assertEqual(self.article.audit_logs.count(), 1)

    def test_head_does_not_increment_views(self) -> None:
        self.assertEqual(self.client.head(self.detail_url).status_code, 200)
        self.article.refresh_from_db()
        self.assertEqual(self.article.views, 0)

    def test_missing_article_returns_404(self) -> None:
        self.assertEqual(
            self.client.get(self.reverse("articles:detail", args=[99999])).status_code,
            404,
        )

    def test_edit_publish_and_archive_record_operator(self) -> None:
        for state, action in (("published", "publish"), ("archived", "archive")):
            response = self.client.post(
                self.edit_url,
                {
                    "title": "编辑后的标题",
                    "content": "编辑正文",
                    "status": state,
                },
            )
            self.assertEqual(response.status_code, 302)
            self.article.refresh_from_db()
            log = self.article.audit_logs.first()
            self.assertEqual(log.action, action)
            self.assertEqual(log.operator_id, self.owner.pk)
            self.assertEqual(self.article.author_id, self.owner.pk)

    def test_other_user_can_read_but_cannot_modify_article_or_upload(self) -> None:
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.detail_url).status_code, 200)
        for url in (self.edit_url, self.delete_url, self.upload_url):
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.post(url, {"title": "入侵"}).status_code, 403
                )
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, "网页测试文章")
        self.assertEqual(self.article.audit_logs.count(), 1)

    def test_delete_get_is_confirmation_and_post_keeps_audit(self) -> None:
        self.assertEqual(self.client.get(self.delete_url).status_code, 200)
        self.assertTrue(Article.objects.filter(pk=self.article.pk).exists())
        response = self.client.post(self.delete_url)
        self.assertRedirects(response, self.reverse("articles:list"))
        self.assertFalse(Article.objects.filter(pk=self.article.pk).exists())
        self.assertEqual(
            AuditLog.objects.get(action="delete").operator_id, self.owner.pk
        )

    def test_csrf_is_required_for_deletion(self) -> None:
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        self.assertEqual(client.post(self.delete_url).status_code, 403)
        self.assertTrue(Article.objects.filter(pk=self.article.pk).exists())

    def test_audit_failure_rolls_back_web_article_save(self) -> None:
        from unittest.mock import patch

        from django.db import DatabaseError

        with patch("articles.signals.AuditLog.objects.using") as manager:
            manager.return_value.create.side_effect = DatabaseError("审计失败")
            with self.assertRaisesMessage(DatabaseError, "审计失败"):
                self.client.post(
                    self.edit_url,
                    {
                        "title": "不应保存",
                        "content": "正文",
                        "status": "draft",
                    },
                )
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, "网页测试文章")

    def upload_attachment(self) -> Attachment:
        response = self.client.post(
            self.upload_url,
            {
                "filename": "测试附件",
                "file": SimpleUploadedFile(
                    "note.txt", b"file contents", content_type="text/plain"
                ),
            },
        )
        self.assertEqual(response.status_code, 302)
        return self.article.attachments.get()

    def test_upload_stores_file_and_detail_shows_filename(self) -> None:
        attachment = self.upload_attachment()
        self.assertTrue(attachment.file.name.startswith("attachments/"))
        self.assertTrue(Path(attachment.file.path).is_file())
        self.assertContains(self.client.get(self.detail_url), "测试附件")

    def test_upload_requires_a_file(self) -> None:
        response = self.client.post(self.upload_url, {"filename": "缺少文件"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertFalse(Attachment.objects.exists())

    def test_download_returns_original_bytes(self) -> None:
        attachment = self.upload_attachment()
        response = self.client.get(
            self.reverse("articles:download", args=[attachment.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"file contents")
        self.assertIn("attachment", response["Content-Disposition"])
        response.close()

    def test_attachment_delete_is_post_only_and_author_only(self) -> None:
        attachment = self.upload_attachment()
        url = self.reverse("articles:attachment-delete", args=[attachment.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.assertTrue(Attachment.objects.filter(pk=attachment.pk).exists())
        self.client.force_login(self.owner)
        path = Path(attachment.file.path)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.client.post(url).status_code, 302)
        self.assertFalse(Attachment.objects.filter(pk=attachment.pk).exists())
        self.assertFalse(path.exists())

    def test_missing_file_returns_404(self) -> None:
        attachment = self.upload_attachment()
        Path(attachment.file.path).unlink()
        response = self.client.get(
            self.reverse("articles:download", args=[attachment.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_template_escapes_untrusted_title(self) -> None:
        self.article.title = "<script>alert(1)</script>"
        self.article.save(update_fields=["title"])
        response = self.client.get(self.detail_url)
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")
        self.assertNotContains(response, "<script>alert(1)</script>")

    def test_detail_logs_are_newest_first(self) -> None:
        self.article.title = "第二个标题"
        self.article.save(update_fields=["title"])
        response = self.client.get(self.detail_url)
        logs = list(response.context["audit_logs"])
        self.assertEqual([log.action for log in logs], ["update", "create"])

    def test_login_and_post_logout(self) -> None:
        self.owner.set_password("test-only-password")
        self.owner.save(update_fields=["password"])
        self.client.logout()
        response = self.client.post(
            self.reverse("login"),
            {
                "username": "owner",
                "password": "test-only-password",
            },
        )
        self.assertRedirects(response, self.reverse("articles:list"))
        self.assertEqual(self.client.get(self.reverse("logout")).status_code, 405)
        self.assertRedirects(
            self.client.post(self.reverse("logout")), self.reverse("login")
        )


class AdminAuditTests(TestCase):
    def setUp(self) -> None:
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory

        from .admin import ArticleAdmin

        self.owner = get_user_model().objects.create_user(username="author")
        self.staff = get_user_model().objects.create_superuser(username="manager")
        self.article = Article.objects.create(
            title="后台文章",
            content="原正文",
            author=self.owner,
        )
        self.request = RequestFactory().post("/admin/")
        self.request.user = self.staff
        self.admin = ArticleAdmin(Article, AdminSite())

    def test_admin_save_records_staff_instead_of_author(self) -> None:
        from .forms import ArticleForm

        self.article.title = "管理员编辑"
        self.admin.save_model(self.request, self.article, ArticleForm(), change=True)
        self.assertEqual(self.article.audit_logs.first().operator_id, self.staff.pk)
        self.assertEqual(self.article.author_id, self.owner.pk)

    def test_admin_edit_does_not_overwrite_concurrent_views(self) -> None:
        from .forms import ArticleForm

        Article.objects.filter(pk=self.article.pk).update(views=5)
        self.article.title = "旧实例编辑"
        self.admin.save_model(self.request, self.article, ArticleForm(), change=True)
        self.article.refresh_from_db()
        self.assertEqual(self.article.views, 5)

    def test_admin_create_sets_author_and_operator(self) -> None:
        from .forms import ArticleForm

        article = Article(title="后台新建", content="正文")
        self.admin.save_model(self.request, article, ArticleForm(), change=False)
        self.assertEqual(article.author, self.staff)
        self.assertEqual(article.audit_logs.get().operator_id, self.staff.pk)

    def test_admin_bulk_delete_passes_actual_operator(self) -> None:
        self.admin.delete_queryset(
            self.request, Article.objects.filter(pk=self.article.pk)
        )
        self.assertEqual(
            AuditLog.objects.get(action="delete").operator_id, self.staff.pk
        )

    def test_audit_admin_is_read_only(self) -> None:
        from django.contrib.admin.sites import AdminSite

        from .admin import AuditLogAdmin

        admin = AuditLogAdmin(AuditLog, AdminSite())
        self.assertFalse(admin.has_add_permission(self.request))
        self.assertFalse(admin.has_change_permission(self.request))
        self.assertFalse(admin.has_delete_permission(self.request))


class InterleavedEditTests(TestCase):
    def test_web_edit_preserves_view_increment_after_form_load(self) -> None:
        from unittest.mock import patch

        from django.db.models import F
        from django.urls import reverse

        from .forms import ArticleForm

        owner = get_user_model().objects.create_user(username="interleaving")
        article = Article.objects.create(title="原标题", content="正文", author=owner)
        self.client.force_login(owner)
        original_save = ArticleForm.save

        def save_after_view_increment(
            form: ArticleForm, commit: bool = True
        ) -> Article:
            result = original_save(form, commit=commit)
            Article.objects.filter(pk=article.pk).update(views=F("views") + 4)
            return result

        with patch.object(
            ArticleForm, "save", autospec=True, side_effect=save_after_view_increment
        ):
            response = self.client.post(
                reverse("articles:edit", args=[article.pk]),
                {
                    "title": "更新标题",
                    "content": "正文",
                    "status": "draft",
                },
            )
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.views, 4)
        self.assertEqual(article.title, "更新标题")
        self.assertEqual(article.audit_logs.count(), 2)


class AdminRequestTests(TestCase):
    def setUp(self) -> None:
        self.owner = get_user_model().objects.create_user(username="article_owner")
        self.manager = get_user_model().objects.create_superuser(
            username="admin_manager"
        )
        self.article = Article.objects.create(
            title="后台请求文章",
            content="正文",
            author=self.owner,
        )
        self.client.force_login(self.manager)

    def test_admin_http_edit_preserves_author_and_records_manager(self) -> None:
        response = self.client.post(
            f"/admin/articles/article/{self.article.pk}/change/",
            {
                "title": "后台归档",
                "content": "正文",
                "status": "archived",
                "_save": "保存",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.article.refresh_from_db()
        self.assertEqual(self.article.author_id, self.owner.pk)
        log = self.article.audit_logs.first()
        self.assertEqual(log.action, "archive")
        self.assertEqual(log.operator_id, self.manager.pk)

    def test_admin_http_delete_keeps_snapshot_and_actual_operator(self) -> None:
        pk = self.article.pk
        response = self.client.post(
            f"/admin/articles/article/{pk}/delete/",
            {"post": "yes"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Article.objects.filter(pk=pk).exists())
        log = AuditLog.objects.get(action="delete")
        self.assertEqual(log.operator_id, self.manager.pk)
        self.assertEqual(log.changes["id"]["old"], str(pk))
        self.assertEqual(AuditLog.objects.count(), 2)

    def test_admin_audit_list_and_detail_are_readable_but_not_editable(self) -> None:
        log = self.article.audit_logs.get()
        url = f"/admin/articles/auditlog/{log.pk}/change/"
        self.assertEqual(self.client.get("/admin/articles/auditlog/").status_code, 200)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {"action": "delete"}).status_code, 403)
        log.refresh_from_db()
        self.assertEqual(log.action, "create")
