from django.templatetags.static import static
from django.utils.html import format_html

from wagtail import hooks


@hooks.register("insert_global_admin_js")
def block_reference_patch_js():
    return format_html(
        '<script src="{}"></script>', static("wagtail_block_reference/js/patch.js")
    )
