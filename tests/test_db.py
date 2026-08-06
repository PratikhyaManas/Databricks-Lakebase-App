import pytest


def test_fetch_notes_empty(db_module):
    page = db_module.fetch_notes()
    assert page.items == []
    assert page.total == 0
    assert page.total_pages == 1
    assert not page.has_next
    assert not page.has_prev


def test_insert_and_fetch_note(db_module):
    db_module.insert_note("first note")
    db_module.insert_note("second note")

    page = db_module.fetch_notes()
    assert page.total == 2
    contents = [n[1] for n in page.items]
    assert contents == ["second note", "first note"]  # newest first


def test_insert_note_rejects_blank(db_module):
    with pytest.raises(ValueError):
        db_module.insert_note("   ")


def test_insert_note_truncates_long_content(db_module):
    db_module.insert_note("x" * 500)
    page = db_module.fetch_notes()
    assert len(page.items[0][1]) == 280


def test_delete_note(db_module):
    db_module.insert_note("to delete")
    note_id = db_module.fetch_notes().items[0][0]
    db_module.delete_note(note_id)
    assert db_module.fetch_notes().total == 0


def test_fetch_orders_returns_rows(db_module):
    page, error = db_module.fetch_orders()
    assert error is None
    assert page.total == 2
    assert page.items[0][1] == "Ava Chen"


def test_fetch_orders_missing_table_returns_friendly_error(db_module, fake_db):
    fake_db.orders_table_exists = False
    page, error = db_module.fetch_orders()
    assert page.items == []
    assert error is not None
    assert "orders_synced" in error


def test_pagination_math(db_module):
    page = db_module.Page(items=[1, 2, 3], total=25, page=1, page_size=10)
    assert page.total_pages == 3
    assert page.has_next is True
    assert page.has_prev is False
