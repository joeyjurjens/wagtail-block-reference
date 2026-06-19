"""
BlockReference - lazy and cyclic block references for Wagtail.

This module provides the BlockReference class, which enables forward references
and cyclic block graphs in Wagtail's block system.
"""

from contextvars import ContextVar
from importlib import import_module

from django.core import checks

from wagtail.blocks.base import Block

# Targets currently being walked through a BlockReference (keyed on Block._definition_id),
# so that a definition-level walk (check) over a cyclic graph terminates when it re-reaches
# a target already on the stack.
reference_walk_in_progress = ContextVar("block_reference_walk", default=None)

# Pairs of (node, node) being compared by BlockReference.__eq__, so that equality of two
# cyclic block graphs terminates instead of recursing forever.
reference_eq_in_progress = ContextVar("block_reference_eq", default=None)


class BlockReference:
    """
    A lazy stand-in for a block, resolved on first use. This is the single mechanism behind
    forward references and cyclic block graphs; the target need not exist at declaration
    time::

        class CommentBlock(blocks.StructBlock):
            text = blocks.CharBlock()
            replies = blocks.ListBlock(blocks.BlockReference(lambda: CommentBlock))

    It is a proxy, not a Block: value operations and ``child_blocks`` are forwarded to the
    resolved target via ``__getattr__``, so at runtime it behaves exactly as the block it
    points to; that recursion is bounded by the (finite) data. ``check`` is forwarded too,
    wrapped in a visited set so a cycle terminates, and reports a resolution failure as
    ``wagtailcore.E009``.

    A reference does not appear in migrations: the lookup builder serialises it as its
    target, so a back-edge becomes a plain index pointing at an ancestor.
    """

    def __init__(self, to):
        self._to = to
        self._resolved = None
        self.name = ""
        # Share Block's global creation counter so a class-level reference sorts correctly
        # alongside Block instances in the declarative metaclass.
        self.creation_counter = Block.creation_counter
        Block.creation_counter += 1

    def resolve(self):
        # Resolve the target (a dotted import path, a Block subclass, or a callable
        # returning either) to a block instance, once, and memoise it.
        if self._resolved is None:
            to = self._to
            if isinstance(to, str):
                module_name, _, class_name = to.rpartition(".")
                to = getattr(import_module(module_name), class_name)
            if isinstance(to, type):
                self._resolved = to()
            elif callable(to):
                result = to()
                self._resolved = result if isinstance(result, Block) else result()
            else:
                raise TypeError(
                    f"BlockReference expected a callable or dotted import path; got {self._to!r}."
                )
            if self.name:
                self._resolved.set_name(self.name)
        return self._resolved

    @property
    def __class__(self):
        # Overriding __class__ to report the wrapped object's type is the same proxy trick
        # Django uses in LazyObject: isinstance()-based dispatch elsewhere then treats a
        # reference exactly like the block it points to. While the target is not yet resolvable
        # -- a forward or self reference during class definition -- this falls back to the real
        # type, so it never raises and the order of any isinstance() check stays irrelevant.
        try:
            return self.resolve().__class__
        except Exception:  # noqa: BLE001 - not resolvable yet; behave as a plain reference
            return type(self)

    def __getattr__(self, name):
        # Runs only for attributes not defined on the proxy. Guard the internal names so a
        # half-initialised proxy (or a copy/pickle) does not recurse via resolve(); forward
        # everything else (the whole value API and child_blocks) to the target.
        if name in ("_to", "_resolved"):
            raise AttributeError(name)
        return getattr(self.resolve(), name)

    def __eq__(self, other):
        # __getattr__ does not forward dunders, so the comparison protocol is implemented
        # here. Two references (or a reference and a block) are equal when their resolved
        # targets are. Comparison is coinductive: record the (node, node) pairs on the
        # comparison stack and, on meeting one again, treat it as equal (matched so far).
        # Keyed on _definition_id so the fresh instances a lookup produces line up.
        if isinstance(other, BlockReference):
            other = other.resolve()
        if not isinstance(other, Block):
            return NotImplemented
        resolved = self.resolve()

        pair = (resolved._definition_id, other._definition_id)
        seen = reference_eq_in_progress.get()
        token = None
        if seen is None:
            seen = set()
            token = reference_eq_in_progress.set(seen)
        try:
            if pair in seen:
                return True
            seen.add(pair)
            try:
                return resolved == other
            finally:
                seen.discard(pair)
        finally:
            if token is not None:
                reference_eq_in_progress.reset(token)

    # Defining __eq__ makes this unhashable by default, matching Block.
    __hash__ = None

    def set_name(self, name):
        self.name = name
        if self._resolved is not None:
            self._resolved.set_name(name)

    def check(self, **kwargs):
        # A reference can fail to resolve in several ways (ImportError, AttributeError, a
        # raising lambda). A check() must turn any such failure into an error to report and
        # never raise, or `manage.py check` crashes with a traceback; the original exception
        # is included so the message stays accurate.
        try:
            self.resolve()
        except Exception as exc:  # noqa: BLE001 - a check reports failures, it must not raise
            return [
                checks.Error(
                    f"BlockReference could not resolve its target {self._to!r}: {exc}",
                    obj=self,
                    id="wagtailcore.E009",
                )
            ]
        return self.forward_walk("check", [], **kwargs)

    def forward_walk(self, method, on_reentry, **kwargs):
        # Forward a definition-level walk to the target, but stop if the target is already
        # being walked higher up the stack, so a cycle terminates. Keyed on _definition_id
        # so the fresh instances a reference resolves to line up across the recursion.
        target = self.resolve()
        seen = reference_walk_in_progress.get()
        token = None
        if seen is None:
            seen = set()
            token = reference_walk_in_progress.set(seen)
        try:
            if target._definition_id in seen:
                return on_reentry
            seen.add(target._definition_id)
            return getattr(target, method)(**kwargs)
        finally:
            if token is not None:
                reference_walk_in_progress.reset(token)
