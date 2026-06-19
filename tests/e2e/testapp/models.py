from django.db import models

from wagtail.admin.panels import FieldPanel
from wagtail.blocks import CharBlock, ListBlock, StreamBlock, StructBlock
from wagtail.fields import StreamField
from wagtail.snippets.models import register_snippet
from wagtail_block_reference import BlockReference


class CommentBlock(StructBlock):
    """Self-referential cyclic block: replies are a list of CommentBlocks."""

    text = CharBlock()
    replies = ListBlock(BlockReference(lambda: CommentBlock), required=False)

    class Meta:
        icon = "comment"


class ContentBlock(StreamBlock):
    comment = CommentBlock()
    text = CharBlock()


@register_snippet
class TestSnippet(models.Model):
    title = models.CharField(max_length=255)
    body = StreamField(ContentBlock(), use_json_field=True, blank=True)

    panels = [FieldPanel("title"), FieldPanel("body")]

    def __str__(self):
        return self.title
