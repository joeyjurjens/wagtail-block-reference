import pytest


@pytest.fixture()
def js_errors(admin_page):
    page, _ = admin_page
    errors = []
    page.on(
        "console", lambda msg: errors.append(msg.text) if msg.type == "error" else None
    )
    page.on("pageerror", lambda err: errors.append(str(err)))
    return page, errors


def _add_comment_block(page):
    page.locator(".c-sf-add-button").first.click()
    page.locator(".w-combobox__option", has_text="Comment").first.click()
    page.wait_for_selector("input[name$='-value-text']")


def _add_reply(page, count_field_name):
    """Click the add button of the ListBlock identified by its count field name."""
    page.evaluate(
        """
        (name) => {
            var inp = document.querySelector('input[name="' + name + '"]');
            var container = inp.parentElement.querySelector('[data-streamfield-list-container]');
            container.querySelector('[data-streamfield-list-add]').click();
        }
    """,
        count_field_name,
    )


def _assert_no_stack_errors(errors, context=""):
    stack = [e for e in errors if "call stack" in e.lower() or "maximum" in e.lower()]
    assert stack == [], f"JS errors{' ' + context if context else ''}: {stack}"


def test_patch_js_injected_on_admin_pages(admin_page):
    """patch.js is injected on every admin page (including pages without a StreamField)."""
    page, base_url = admin_page
    page.goto(f"{base_url}/admin/")
    page.wait_for_load_state("networkidle")

    assert page.evaluate("!!window.telepath?.__cyclicUnpackPatched") is True


def test_patch_active_and_editor_renders(js_errors, django_server):
    """On a StreamField page: prototype getters are applied, editor renders, no JS errors."""
    page, errors = js_errors
    page.goto(f"{django_server}/admin/snippets/testapp/testsnippet/add/")
    page.wait_for_load_state("networkidle")

    state = page.evaluate("""
        (() => {
            var tp = window.telepath;
            if (!tp) return { error: 'no telepath' };
            var S = tp.constructors['wagtail.blocks.StructBlock'];
            var St = tp.constructors['wagtail.blocks.StreamBlock'];
            return {
                patched: !!tp.__cyclicUnpackPatched,
                structLazyGetter: typeof Object.getOwnPropertyDescriptor(S?.prototype, 'childBlockDefsByName')?.get === 'function',
                streamLazyGetter: typeof Object.getOwnPropertyDescriptor(St?.prototype, 'childBlockDefsByName')?.get === 'function',
                editorRendered: !!document.querySelector('[data-streamfield-stream-container]'),
            };
        })()
    """)
    assert state.get("error") is None, state.get("error")
    assert state["patched"] is True
    assert state["structLazyGetter"] is True
    assert state["streamLazyGetter"] is True
    assert state["editorRendered"] is True
    _assert_no_stack_errors(errors)


def test_cyclic_block_3_levels_deep_saves(js_errors, django_server):
    """
    Build and save a 3-level-deep CommentBlock tree:

        Root
          replies[0]: Level 1
            replies[0]: Level 2
              replies[0]: Level 3

    Each level uses BlockReference(lambda: CommentBlock).
    Without the JS patch this crashes with 'Maximum call stack size exceeded'.
    """
    page, errors = js_errors
    page.goto(f"{django_server}/admin/snippets/testapp/testsnippet/add/")
    page.wait_for_load_state("networkidle")

    page.fill("input[name='title']", "3-level nested comment")

    _add_comment_block(page)
    page.fill("input[name='body-0-value-text']", "Root")

    _add_reply(page, "body-0-value-replies-count")
    page.wait_for_selector("input[name='body-0-value-replies-0-value-text']")
    page.fill("input[name='body-0-value-replies-0-value-text']", "Level 1")

    _add_reply(page, "body-0-value-replies-0-value-replies-count")
    page.wait_for_selector(
        "input[name='body-0-value-replies-0-value-replies-0-value-text']"
    )
    page.fill(
        "input[name='body-0-value-replies-0-value-replies-0-value-text']", "Level 2"
    )

    _add_reply(page, "body-0-value-replies-0-value-replies-0-value-replies-count")
    page.wait_for_selector(
        "input[name='body-0-value-replies-0-value-replies-0-value-replies-0-value-text']"
    )
    page.fill(
        "input[name='body-0-value-replies-0-value-replies-0-value-replies-0-value-text']",
        "Level 3",
    )

    _assert_no_stack_errors(errors, "before save")

    page.locator("button.action-save").click()
    page.wait_for_load_state("networkidle")

    assert page.locator("li.error").count() == 0, "Validation errors on save"
    assert page.locator("li.success").count() > 0, "No success message after save"
    _assert_no_stack_errors(errors, "after save")

    # Re-open the saved snippet and verify all 4 levels persisted
    page.locator("li.success a").first.click()
    page.wait_for_load_state("networkidle")

    assert page.locator("input[name='body-0-value-text']").input_value() == "Root"
    assert (
        page.locator("input[name='body-0-value-replies-0-value-text']").input_value()
        == "Level 1"
    )
    assert (
        page.locator(
            "input[name='body-0-value-replies-0-value-replies-0-value-text']"
        ).input_value()
        == "Level 2"
    )
    assert (
        page.locator(
            "input[name='body-0-value-replies-0-value-replies-0-value-replies-0-value-text']"
        ).input_value()
        == "Level 3"
    )
    _assert_no_stack_errors(errors, "after reopen")
