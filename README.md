# wagtail-block-reference

BlockReference support for Wagtail — enables forward and cyclic block references.

> **Heads up:** this package is quite hacky. It works by monkey-patching Wagtail internals
> (Python and JS), which is inherently fragile. It exists because the upstream PR
> ([wagtail#14279](https://github.com/wagtail/wagtail/pull/14279)) may take a while to land
> (if it ever does), and waiting wasn't an option for me :). The test suite deliberately targets the
> patched internals so that a future Wagtail upgrade that breaks the patches fails loudly
> rather than silently misbehaving.

## Installation

```bash
pip install wagtail-block-reference
```

Add to `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    ...
    "wagtail_block_reference",
]
```

## Usage

```python
from wagtail import blocks
from wagtail_block_reference import BlockReference

class CommentBlock(blocks.StructBlock):
    text = blocks.CharBlock()
    replies = blocks.ListBlock(BlockReference(lambda: CommentBlock))
```

## How it works

`BlockReference` is a lazy proxy that resolves its target block on first access. The target
can be a lambda (for forward/cyclic references), a dotted import path, or a block class.

The package ships two patches:

**Python patch** (`patches.py`, applied at import time): hooks into Wagtail's block
metaclass so that `BlockReference` attributes declared on a `StructBlock` are collected as
child blocks, and registers a telepath adapter so the block serialises as its resolved target.

**JS patch** (`patch.js`, injected via `insert_global_admin_js`): intercepts `window.telepath`
before Wagtail's own bundles load, then wraps `StructBlock` and `StreamBlock` prototypes with
a lazy `childBlockDefsByName` getter. Without this, the cyclic telepath graph causes a
`Maximum call stack size exceeded` crash when the editor tries to build the block name map
at construction time.

## Supported versions

All Wagtail versions that are currently under active or security support: 7.0 LTS, 7.3, and 7.4 LTS. CI tests against each of these. Versions drop off the matrix as they go end-of-life.

## Development

```bash
# Install dependencies
uv sync

# Lint & format
uv run ruff check .
uv run ruff format .

# Run all tests (unit + E2E) against a single Wagtail version
uv run playwright install chromium
uv run pytest tests/

# Run all tests against all supported Wagtail versions (installs Chromium automatically)
uv run tox

# Run all tests against all supported Wagtail versions (installs Chromium automatically)
# and see visually what the browser is doing
uv run tox  -- --headed --slowmo=500

# Run against a specific version
uv run tox -e wagtail74

# Run against a specific version and see visually what the browser is doing
uv run tox -e wagtail74 -- --headed --slowmo=500
```

## License

MIT
