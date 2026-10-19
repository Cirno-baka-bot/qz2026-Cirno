import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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

    def test_detail_logs_are_newest_first(self) -> None:
        self.article.title = "第二个标题"
        self.article.save(update_fields=["title"])
        response = self.client.get(self.detail_url)
        logs = list(response.context["audit_logs"])
        self.assertEqual([log.action for log in logs], ["update", "create"])


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
