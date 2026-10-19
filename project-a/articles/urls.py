from django.urls import path

from . import views

app_name = "articles"

urlpatterns = [
    path("", views.article_list, name="list"),
    path("articles/new/", views.article_create, name="create"),
    path("articles/<int:pk>/", views.article_detail, name="detail"),
    path("articles/<int:pk>/edit/", views.article_edit, name="edit"),
    path("articles/<int:pk>/delete/", views.article_delete, name="delete"),
    path("articles/<int:pk>/attachments/", views.attachment_upload, name="upload"),
    path("attachments/<int:pk>/download/", views.attachment_download, name="download"),
    path(
        "attachments/<int:pk>/delete/",
        views.attachment_delete,
        name="attachment-delete",
    ),
]
