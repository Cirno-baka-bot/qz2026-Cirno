from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import (
    require_http_methods,
    require_POST,
    require_safe,
)

from .forms import ArticleForm, AttachmentForm
from .models import Article, Attachment


@login_required
@require_safe
def article_list(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "articles/list.html",
        {
            "articles": Article.objects.select_related("author").all(),
        },
    )


@login_required
@require_safe
def article_detail(request: HttpRequest, pk: int) -> HttpResponse:
    if request.method == "GET":
        updated = Article.objects.filter(pk=pk).update(views=F("views") + 1)
        if not updated:
            raise Http404("文章不存在")
    article = get_object_or_404(Article.objects.select_related("author"), pk=pk)
    return render(
        request,
        "articles/detail.html",
        {
            "article": article,
            "attachments": article.attachments.all(),
            "audit_logs": article.audit_logs.select_related("operator").all(),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def article_create(request: HttpRequest) -> HttpResponse:
    form = ArticleForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        article = form.save(commit=False)
        article.author = request.user
        article._audit_actor_id = request.user.pk
        article.save()
        messages.success(request, "文章已创建。")
        return redirect("articles:detail", pk=article.pk)
    return render(request, "articles/form.html", {"form": form, "heading": "新建文章"})


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def article_edit(request: HttpRequest, pk: int) -> HttpResponse:
    article = get_object_or_404(Article.objects.select_for_update(), pk=pk)
    if article.author_id != request.user.pk:
        raise PermissionDenied("只有作者可以修改文章。")
    form = ArticleForm(
        request.POST if request.method == "POST" else None,
        instance=article,
    )
    if request.method == "POST" and form.is_valid():
        article = form.save(commit=False)
        article._audit_actor_id = request.user.pk
        article.save(update_fields=["title", "content", "status", "updated_at"])
        messages.success(request, "文章已保存。")
        return redirect("articles:detail", pk=article.pk)
    return render(
        request,
        "articles/form.html",
        {
            "form": form,
            "heading": "编辑文章",
            "article": article,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
@transaction.atomic
def article_delete(request: HttpRequest, pk: int) -> HttpResponse:
    article = get_object_or_404(Article.objects.select_for_update(), pk=pk)
    if article.author_id != request.user.pk:
        raise PermissionDenied("只有作者可以删除文章。")
    if request.method == "POST":
        article._audit_actor_id = request.user.pk
        article.delete()
        messages.success(request, "文章已删除，操作记录已保留。")
        return redirect("articles:list")
    return render(request, "articles/confirm_delete.html", {"article": article})


@login_required
@require_POST
@transaction.atomic
def attachment_upload(request: HttpRequest, pk: int) -> HttpResponse:
    article = get_object_or_404(Article, pk=pk)
    if article.author_id != request.user.pk:
        raise PermissionDenied("只有作者可以上传附件。")
    form = AttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        attachment = form.save(commit=False)
        attachment.article = article
        attachment.save()
        messages.success(request, "附件已上传。")
        return redirect("articles:detail", pk=article.pk)
    return render(request, "articles/upload.html", {"article": article, "form": form})


@login_required
@require_safe
def attachment_download(request: HttpRequest, pk: int) -> FileResponse:
    attachment = get_object_or_404(Attachment, pk=pk)
    try:
        source = attachment.file.open("rb")
    except FileNotFoundError as error:
        raise Http404("附件文件不存在") from error
    return FileResponse(
        source,
        as_attachment=True,
        filename=Path(attachment.file.name).name,
    )


@login_required
@require_POST
@transaction.atomic
def attachment_delete(request: HttpRequest, pk: int) -> HttpResponse:
    attachment = get_object_or_404(Attachment.objects.select_related("article"), pk=pk)
    if attachment.article.author_id != request.user.pk:
        raise PermissionDenied("只有作者可以删除附件。")
    article_id = attachment.article_id
    attachment.delete()
    messages.success(request, "附件已删除。")
    return redirect("articles:detail", pk=article_id)
