from django import forms

from .models import Article, Attachment


class ArticleForm(forms.ModelForm):
    class Meta:
        model = Article
        fields = ("title", "content", "status")
        labels = {"title": "标题"}
        widgets = {"content": forms.Textarea(attrs={"rows": 12})}


class AttachmentForm(forms.ModelForm):
    class Meta:
        model = Attachment
        fields = ("filename", "file")
