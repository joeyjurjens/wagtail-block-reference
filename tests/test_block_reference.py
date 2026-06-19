import copy

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from wagtail import blocks
from wagtail.blocks.definition_lookup import (
    BlockDefinitionLookup,
    BlockDefinitionLookupBuilder,
)
from wagtail_block_reference import BlockReference


def roundtrip(block):
    builder = BlockDefinitionLookupBuilder()
    index = builder.add_block(block)
    return BlockDefinitionLookup(builder.get_lookup_as_dict()).get_block(index)


class TestBlockReferenceProxy(SimpleTestCase):
    def setUp(self):
        class CommentBlock(blocks.StructBlock):
            text = blocks.CharBlock(required=True)
            replies = blocks.ListBlock(BlockReference(lambda: CommentBlock))

        self.CommentBlock = CommentBlock

    def test_reference_presents_as_its_target_class(self):
        ref = BlockReference(lambda: blocks.CharBlock)
        self.assertIsInstance(ref, blocks.CharBlock)
        self.assertIsInstance(ref, blocks.Block)
        self.assertIs(type(ref), BlockReference)

        struct_ref = self.CommentBlock().child_blocks["replies"].child_block
        self.assertIsInstance(struct_ref, blocks.StructBlock)
        self.assertNotIsInstance(struct_ref, blocks.ListBlock)

    def test_invalid_target_raises(self):
        with self.assertRaises(TypeError):
            BlockReference(42).resolve()

    def test_dotted_path_target_resolves(self):
        ref = BlockReference("wagtail.blocks.CharBlock")
        self.assertIsInstance(ref, blocks.CharBlock)

    def test_callable_target_can_return_a_configured_block(self):
        optional = BlockReference(
            lambda: blocks.CharBlock(required=False, max_length=5)
        )
        self.assertFalse(optional.required)
        self.assertEqual(optional.field.max_length, 5)

        default = BlockReference(lambda: blocks.CharBlock)
        self.assertTrue(default.required)

    def test_target_is_resolved_once_and_memoised(self):
        ref = BlockReference(lambda: blocks.CharBlock)
        self.assertIs(ref.resolve(), ref.resolve())

    def test_set_name_propagates_through_resolution(self):
        ref = BlockReference(lambda: blocks.CharBlock)
        ref.set_name("foo")
        self.assertEqual(ref.resolve().name, "foo")

    def test_deepcopy_preserves_unresolved_reference(self):
        ref = BlockReference(lambda: blocks.CharBlock)
        copied = copy.deepcopy(ref)
        self.assertIs(type(copied), BlockReference)
        self.assertIsInstance(copied.resolve(), blocks.CharBlock)

    def test_directly_declared_reference_is_collected(self):
        # Exercises the metaclass patch: a forward reference declared as a class
        # attribute must be collected as a child block.
        class PageBlock(blocks.StructBlock):
            title = blocks.CharBlock()
            related = BlockReference(lambda: PageBlock)

        self.assertEqual(set(PageBlock().child_blocks), {"title", "related"})

    def test_forward_reference(self):
        class AccordionBlock(blocks.StructBlock):
            heading = blocks.CharBlock()

        class ContentBlock(blocks.StreamBlock):
            accordion = AccordionBlock()
            paragraph = blocks.RichTextBlock()

        accordion = AccordionBlock([("content", BlockReference(lambda: ContentBlock))])
        content = accordion.child_blocks["content"]
        self.assertIsInstance(content, blocks.StreamBlock)
        self.assertIn("accordion", content.child_blocks)

    def test_inherited_reference_resolves(self):
        class BaseBlock(blocks.StructBlock):
            children = blocks.ListBlock(BlockReference(lambda: BaseBlock))

        class SubBlock(BaseBlock):
            extra = blocks.CharBlock()

        self.assertEqual(SubBlock().check(), [])
        self.assertEqual(set(SubBlock().child_blocks), {"children", "extra"})


class TestCyclicBlockBehaviour(SimpleTestCase):
    def setUp(self):
        class CommentBlock(blocks.StructBlock):
            text = blocks.CharBlock(required=True)
            replies = blocks.ListBlock(BlockReference(lambda: CommentBlock))

        self.CommentBlock = CommentBlock

    def test_self_referential_block_supports_core_operations(self):
        block = self.CommentBlock()
        self.assertEqual(block.check(), [])

        default = block.get_default()
        self.assertIn("text", default)
        self.assertEqual(list(default["replies"]), [])

        value = block.to_python(
            {
                "text": "L0",
                "replies": [{"text": "L1", "replies": [{"text": "L2", "replies": []}]}],
            }
        )
        self.assertEqual(value["replies"][0]["replies"][0]["text"], "L2")

        prepped = block.get_prep_value(value)
        self.assertEqual(
            prepped["replies"][0]["value"]["replies"][0]["value"]["text"], "L2"
        )

    def test_defer_and_restore_validation_terminates(self):
        # StreamBlock/StructBlock walk child_blocks for defer/restore; a cyclic
        # BlockReference must not cause an infinite loop.
        block = self.CommentBlock()
        block.defer_required_validation()
        block.restore_deferred_validation()

    def test_deferred_validation_terminates_through_cycle(self):
        # Empty required text passes while deferred, then fails once validation is restored.
        block = self.CommentBlock()
        value = block.to_python(
            {"text": "ok", "replies": [{"text": "", "replies": []}]}
        )
        block.clean_deferred(value)
        with self.assertRaises(ValidationError):
            block.clean(value)

        # The same across a mutual reference.
        class AuthorBlock(blocks.StructBlock):
            name = blocks.CharBlock(required=True)
            posts = blocks.ListBlock(BlockReference(lambda: PostBlock))

        class PostBlock(blocks.StructBlock):
            authors = blocks.ListBlock(BlockReference(lambda: AuthorBlock))

        author = AuthorBlock()
        author_value = author.to_python({"name": "", "posts": []})
        author.clean_deferred(author_value)
        with self.assertRaises(ValidationError):
            author.clean(author_value)

    def test_deferred_validation_reaches_forward_referenced_block(self):
        class PageBlock(blocks.StructBlock):
            title = blocks.CharBlock()
            author = BlockReference(lambda: AuthorBlock)

        class AuthorBlock(blocks.StructBlock):
            name = blocks.CharBlock(required=True)

        block = PageBlock()
        value = block.to_python({"title": "hi", "author": {"name": ""}})

        block.clean_deferred(value)  # must not raise: the author's required is deferred

        with self.assertRaises(ValidationError):
            block.clean(value)  # restored: required is enforced again

    def test_overridden_defer_restore_reached_through_reference(self):
        # A target that overrides the deferred-validation hooks is still driven
        # correctly when reached through a reference.
        calls = []

        class CustomBlock(blocks.StructBlock):
            name = blocks.CharBlock(required=True)

            def defer_required_validation(self):
                calls.append("defer")
                super().defer_required_validation()

            def restore_deferred_validation(self):
                calls.append("restore")
                super().restore_deferred_validation()

        class PageBlock(blocks.StructBlock):
            custom = BlockReference(lambda: CustomBlock)

        ref = PageBlock().child_blocks["custom"]
        ref.defer_required_validation()
        ref.restore_deferred_validation()
        self.assertEqual(calls, ["defer", "restore"])

    def test_mutual_reference_terminates(self):
        class AuthorBlock(blocks.StructBlock):
            name = blocks.CharBlock()
            posts = blocks.ListBlock(BlockReference(lambda: PostBlock))

        class PostBlock(blocks.StructBlock):
            title = blocks.CharBlock()
            authors = blocks.ListBlock(BlockReference(lambda: AuthorBlock))

        self.assertEqual(AuthorBlock().check(), [])
        self.assertEqual(list(AuthorBlock().get_default()["posts"]), [])

    def test_value_from_datadict_terminates(self):
        block = self.CommentBlock()
        data = {
            "comment-text": "hello",
            "comment-replies-count": "1",
            "comment-replies-0-deleted": "",
            "comment-replies-0-order": "0",
            "comment-replies-0-id": "reply-1",
            "comment-replies-0-value-text": "a reply",
            "comment-replies-0-value-replies-count": "0",
        }
        value = block.value_from_datadict(data, {}, "comment")
        self.assertEqual(value["text"], "hello")
        reply = list(value["replies"])[0]
        self.assertEqual(reply["text"], "a reply")
        self.assertEqual(list(reply["replies"]), [])

    def test_clean_validates_nested_value_through_reference(self):
        block = self.CommentBlock()
        value = block.to_python(
            {"text": "ok", "replies": [{"text": "", "replies": []}]}
        )
        with self.assertRaises(ValidationError):
            block.clean(value)

    def test_streamblock_self_reference_terminates(self):
        class SectionStream(blocks.StreamBlock):
            text = blocks.CharBlock()
            nested = BlockReference(lambda: SectionStream)

        self.assertEqual(SectionStream().check(), [])
        self.assertEqual(list(SectionStream().get_default()), [])

    def test_cyclic_block_equality(self):
        class OtherBlock(blocks.StructBlock):
            heading = blocks.CharBlock()
            children = blocks.ListBlock(BlockReference(lambda: OtherBlock))

        self.assertEqual(self.CommentBlock(), self.CommentBlock())
        self.assertNotEqual(self.CommentBlock(), OtherBlock())
        self.assertEqual(roundtrip(self.CommentBlock()), self.CommentBlock())


class TestCyclicBlockLookup(SimpleTestCase):
    def test_self_referential_lookup_round_trip(self):
        class CommentBlock(blocks.StructBlock):
            text = blocks.CharBlock()
            replies = blocks.ListBlock(BlockReference(lambda: CommentBlock))

        rebuilt = roundtrip(CommentBlock())
        self.assertIsInstance(rebuilt, blocks.StructBlock)
        self.assertEqual(rebuilt.check(), [])
        child = rebuilt.child_blocks["replies"].child_block
        self.assertIsInstance(child, BlockReference)
        self.assertEqual(set(child.child_blocks), {"text", "replies"})

    def test_mutual_reference_lookup_round_trip(self):
        class AuthorBlock(blocks.StructBlock):
            posts = blocks.ListBlock(BlockReference(lambda: PostBlock))

        class PostBlock(blocks.StructBlock):
            authors = blocks.ListBlock(BlockReference(lambda: AuthorBlock))

        rebuilt = roundtrip(AuthorBlock())
        self.assertEqual(rebuilt.check(), [])

    def test_reference_does_not_appear_in_lookup_table(self):
        class CommentBlock(blocks.StructBlock):
            text = blocks.CharBlock()
            replies = blocks.ListBlock(BlockReference(lambda: CommentBlock))

        builder = BlockDefinitionLookupBuilder()
        builder.add_block(CommentBlock())
        paths = [entry[0] for entry in builder.get_lookup_as_dict().values()]
        self.assertNotIn("wagtail.blocks.BlockReference", paths)

    def test_multiple_references_to_one_block_deduplicated(self):
        class Section(blocks.StructBlock):
            items = blocks.ListBlock(BlockReference(lambda: Item))
            related = blocks.ListBlock(BlockReference(lambda: Item))

        class Item(blocks.StructBlock):
            title = blocks.CharBlock()
            children = blocks.ListBlock(BlockReference(lambda: Section))

        builder = BlockDefinitionLookupBuilder()
        builder.add_block(Section())
        struct_entries = [
            entry
            for entry in builder.get_lookup_as_dict().values()
            if entry and entry[0] == "wagtail.blocks.StructBlock"
        ]
        self.assertEqual(len(struct_entries), 2)  # one Section + one Item, not three

    def test_reconstruct_cycle_entered_through_its_own_list_block(self):
        class CommentBlock(blocks.StructBlock):
            text = blocks.CharBlock()
            replies = blocks.ListBlock(BlockReference(lambda: CommentBlock))

        stream = blocks.StreamBlock(
            [("a", CommentBlock()), ("b", CommentBlock(group="X"))]
        )
        rebuilt = roundtrip(stream)
        self.assertEqual(rebuilt.check(), [])
        rebuilt.get_default()  # must not raise
