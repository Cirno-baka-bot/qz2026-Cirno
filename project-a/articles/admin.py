from django import forms
from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import Article, AuditLog


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "status", "views", "created_at")
    list_filter = ("status",)
    search_fields = ("title",)
    readonly_fields = ("author", "views", "created_at", "updated_at")

    def save_model(
        self,
        request: HttpRequest,
        obj: Article,
        form: forms.ModelForm,
        change: bool,
    ) -> None:
        """后台保存也传递真实操作人，且不覆盖浏览量。"""
        obj._audit_actor_id = request.user.pk
        if change:
            obj.save(update_fields=["title", "content", "status", "updated_at"])
        else:
            obj.author = request.user
            obj.save()

    def delete_model(self, request: HttpRequest, obj: Article) -> None:
        obj._audit_actor_id = request.user.pk
        obj.delete()

    def delete_queryset(
        self,
        request: HttpRequest,
        queryset: QuerySet[Article],
    ) -> None:
        for article in queryset:
            self.delete_model(request, article)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "article", "operator", "created_at")
    list_filter = ("action",)
    readonly_fields = ("action", "article", "operator", "created_at", "changes")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: AuditLog | None = None,
    ) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: AuditLog | None = None,
    ) -> bool:
        return False
