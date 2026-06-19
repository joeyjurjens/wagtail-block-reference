import collections

from telepath import Adapter, ValueContext

try:
    from wagtail.admin.telepath import WagtailJSContextBase, register
except ImportError:
    from wagtail.telepath import WagtailJSContextBase, register
from wagtail.blocks import definition_lookup
from wagtail.blocks.base import BaseBlock, Block, DeclarativeSubBlocksMetaclass
from wagtail.blocks.list_block import ListBlock as _ListBlock
from wagtail.blocks.list_block import ListValue

from .block_reference import BlockReference

_orig_block_init = Block.__init__
_orig_list_bulk_to_python = _ListBlock.bulk_to_python
_orig_lookup_init = definition_lookup.BlockDefinitionLookup.__init__
_orig_lookup_get_block = definition_lookup.BlockDefinitionLookup.get_block
_orig_builder_init = definition_lookup.BlockDefinitionLookupBuilder.__init__


def _block_init(self, **kwargs):
    _orig_block_init(self, **kwargs)
    self._definition_id = id(self)


def _meta_new(mcs, name, bases, attrs):
    current_blocks = []
    for key, value in list(attrs.items()):
        if isinstance(value, (Block, BlockReference)):
            current_blocks.append((key, value))
            value.set_name(key)
            attrs.pop(key)
    current_blocks.sort(key=lambda x: x[1].creation_counter)
    attrs["declared_blocks"] = collections.OrderedDict(current_blocks)
    new_class = BaseBlock.__new__(mcs, name, bases, attrs)
    base_blocks = collections.OrderedDict()
    for base in reversed(new_class.__mro__):
        if hasattr(base, "declared_blocks"):
            base_blocks.update(base.declared_blocks)
        for attr, value in base.__dict__.items():
            if value is None and attr in base_blocks:
                base_blocks.pop(attr)
    new_class.base_blocks = base_blocks
    return new_class


class ListBlock(_ListBlock):
    def __init__(self, child_block, search_index=True, **kwargs):
        Block.__init__(self, **kwargs)
        self.search_index = search_index
        if isinstance(child_block, BlockReference):
            self.child_block = child_block
        elif isinstance(child_block, type):
            self.child_block = child_block()
        else:
            self.child_block = child_block
        self._has_default = hasattr(self.meta, "default")
        if not self._has_default:
            if isinstance(self.child_block, BlockReference):
                self.meta.default = []
            else:
                self.meta.default = lambda: [self.child_block.get_default()]

    def bulk_to_python(self, values):
        if not any(values):
            return [ListValue(self, bound_blocks=[]) for _ in values]
        return _orig_list_bulk_to_python(self, values)


ListBlock.__init__.has_child_block_arg = True


class BlockDefinitionLookup(definition_lookup.BlockDefinitionLookup):
    def __init__(self, blocks):
        _orig_lookup_init(self, blocks)
        self._constructing = set()

    def get_block(self, index):
        if index in self._constructing:
            return BlockReference(lambda i=index: self.get_block(i))
        self._constructing.add(index)
        try:
            block = _orig_lookup_get_block(self, index)
        finally:
            self._constructing.discard(index)
        block._definition_id = index
        return block


class BlockDefinitionLookupBuilder(definition_lookup.BlockDefinitionLookupBuilder):
    def __init__(self):
        _orig_builder_init(self)
        self.block_indexes_by_identity = {}
        self.pending_block_indexes = {}

    def add_block(self, block):
        identity = block._definition_id

        if identity in self.block_indexes_by_identity:
            return self.block_indexes_by_identity[identity]

        if identity in self.pending_block_indexes:
            reserved_index = self.pending_block_indexes[identity]
            if reserved_index is None:
                reserved_index = len(self.blocks)
                self.blocks.append(None)
                self.pending_block_indexes[identity] = reserved_index
            return reserved_index

        self.pending_block_indexes[identity] = None
        deconstructed = block.deconstruct_with_lookup(self)
        reserved_index = self.pending_block_indexes.pop(identity)

        block_indexes = self.block_indexes_by_type[deconstructed[0]]
        if reserved_index is None:
            for existing_index, existing_deconstructed in block_indexes:
                if existing_deconstructed == deconstructed:
                    self.block_indexes_by_identity[identity] = existing_index
                    return existing_index
            index = len(self.blocks)
            self.blocks.append(deconstructed)
        else:
            index = reserved_index
            self.blocks[index] = deconstructed

        self.block_indexes_by_identity[identity] = index
        block_indexes.append((index, deconstructed))
        return index


class _CyclePlaceholder:
    def __init__(self):
        self.id = None
        self.seen = False
        self.use_id = True

    def emit(self):
        return {"_ref": self.id}


class WagtailValueContext(ValueContext):
    def build_node(self, val):
        obj_id = id(val)
        if obj_id in self.nodes:
            existing_node = self.nodes[obj_id]
            if existing_node.id is None:
                existing_node.id = self.next_id
                self.next_id += 1
            return existing_node
        placeholder = _CyclePlaceholder()
        self.nodes[obj_id] = placeholder
        self.raw_values[obj_id] = val
        node = self._build_new_node(val)
        if placeholder.id is not None:
            node.id = placeholder.id
        self.nodes[obj_id] = node
        return node


class BlockReferenceAdapter(Adapter):
    def build_node(self, obj, context):
        return context.build_node(obj.resolve())


Block.__init__ = _block_init
DeclarativeSubBlocksMetaclass.__new__ = _meta_new

_ListBlock.__init__ = ListBlock.__init__
_ListBlock.bulk_to_python = ListBlock.bulk_to_python

definition_lookup.BlockDefinitionLookup.__init__ = BlockDefinitionLookup.__init__
definition_lookup.BlockDefinitionLookup.get_block = BlockDefinitionLookup.get_block

definition_lookup.BlockDefinitionLookupBuilder.__init__ = (
    BlockDefinitionLookupBuilder.__init__
)
definition_lookup.BlockDefinitionLookupBuilder.add_block = (
    BlockDefinitionLookupBuilder.add_block
)

WagtailJSContextBase.pack = lambda self, obj: (
    WagtailValueContext(self).build_node(obj).emit()
)

register(BlockReferenceAdapter(), BlockReference)
