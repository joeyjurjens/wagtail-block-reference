from . import patches as _patches  # noqa: F401
from .block_reference import BlockReference

default_app_config = "wagtail_block_reference.apps.WagtailBlockReferenceAppConfig"

__all__ = ["BlockReference"]
__version__ = "0.1.0"
