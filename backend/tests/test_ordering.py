"""Ordering invariants.

The rule under test, everywhere: within one column, card positions are exactly
0..n-1, in order, with no gaps and no duplicates. Ordering bugs are quiet, so
each test asserts the whole arrangement rather than the one row it moved.
"""

import pytest
from fastapi import HTTPException

from app.services import boards, cards, columns


async def build_board(session, user, column_titles: list[str]):
    board = await boards.create_board(session, user, "Board")
    made = [
        await columns.create_column(session, user, board.id, title)
        for title in column_titles
    ]
    return board, made


async def titles_in(session, column_id) -> list[str]:
    return [card.title for card in await cards.list_cards(session, column_id)]


async def positions_in(session, column_id) -> list[int]:
    return [card.position for card in await cards.list_cards(session, column_id)]


async def assert_contiguous(session, column_id) -> None:
    found = await positions_in(session, column_id)
    assert found == list(range(len(found))), (
        f"positions must be 0..n-1 with no gaps or duplicates, found {found}"
    )


async def fill(session, user, column_id, titles: list[str]):
    return [
        await cards.create_card(session, user, column_id, title, None)
        for title in titles
    ]


async def test_created_cards_append_in_order(session, user):
    _board, (todo,) = await build_board(session, user, ["Todo"])
    await fill(session, user, todo.id, ["a", "b", "c"])

    assert await positions_in(session, todo.id) == [0, 1, 2]
    assert await titles_in(session, todo.id) == ["a", "b", "c"]


async def test_move_within_column_to_first(session, user):
    _board, (todo,) = await build_board(session, user, ["Todo"])
    made = await fill(session, user, todo.id, ["a", "b", "c"])

    await cards.move_card(session, user, made[2].id, todo.id, 0)

    assert await titles_in(session, todo.id) == ["c", "a", "b"]
    await assert_contiguous(session, todo.id)


async def test_move_within_column_to_last(session, user):
    _board, (todo,) = await build_board(session, user, ["Todo"])
    made = await fill(session, user, todo.id, ["a", "b", "c"])

    await cards.move_card(session, user, made[0].id, todo.id, 2)

    assert await titles_in(session, todo.id) == ["b", "c", "a"]
    await assert_contiguous(session, todo.id)


async def test_move_within_column_to_middle(session, user):
    _board, (todo,) = await build_board(session, user, ["Todo"])
    made = await fill(session, user, todo.id, ["a", "b", "c", "d"])

    await cards.move_card(session, user, made[3].id, todo.id, 1)

    assert await titles_in(session, todo.id) == ["a", "d", "b", "c"]
    await assert_contiguous(session, todo.id)


async def test_move_across_columns_closes_the_source_gap(session, user):
    _board, (todo, doing) = await build_board(session, user, ["Todo", "Doing"])
    made = await fill(session, user, todo.id, ["a", "b", "c"])
    await fill(session, user, doing.id, ["x", "y"])

    await cards.move_card(session, user, made[0].id, doing.id, 1)

    assert await titles_in(session, todo.id) == ["b", "c"]
    assert await titles_in(session, doing.id) == ["x", "a", "y"]
    await assert_contiguous(session, todo.id)
    await assert_contiguous(session, doing.id)


async def test_move_into_an_empty_column(session, user):
    _board, (todo, doing) = await build_board(session, user, ["Todo", "Doing"])
    made = await fill(session, user, todo.id, ["a"])

    await cards.move_card(session, user, made[0].id, doing.id, 0)

    assert await titles_in(session, todo.id) == []
    assert await titles_in(session, doing.id) == ["a"]


async def test_move_position_beyond_the_end_is_clamped(session, user):
    _board, (todo, doing) = await build_board(session, user, ["Todo", "Doing"])
    made = await fill(session, user, todo.id, ["a"])
    await fill(session, user, doing.id, ["x", "y"])

    await cards.move_card(session, user, made[0].id, doing.id, 99)

    assert await titles_in(session, doing.id) == ["x", "y", "a"]
    await assert_contiguous(session, doing.id)


async def test_move_to_where_it_already_is_changes_nothing(session, user):
    _board, (todo,) = await build_board(session, user, ["Todo"])
    made = await fill(session, user, todo.id, ["a", "b", "c"])

    await cards.move_card(session, user, made[1].id, todo.id, 1)

    assert await titles_in(session, todo.id) == ["a", "b", "c"]
    await assert_contiguous(session, todo.id)


async def test_deleting_from_the_middle_renumbers(session, user):
    _board, (todo,) = await build_board(session, user, ["Todo"])
    made = await fill(session, user, todo.id, ["a", "b", "c", "d"])

    await cards.delete_card(session, user, made[1].id)

    assert await titles_in(session, todo.id) == ["a", "c", "d"]
    await assert_contiguous(session, todo.id)


async def test_deleting_a_column_renumbers_the_rest(session, user):
    board, made = await build_board(session, user, ["Todo", "Doing", "Done"])

    await columns.delete_column(session, user, made[1].id)

    remaining = await columns.list_columns(session, board.id)
    assert [column.title for column in remaining] == ["Todo", "Done"]
    assert [column.position for column in remaining] == [0, 1]


async def test_cards_created_after_a_move_still_append_to_the_end(session, user):
    _board, (todo, doing) = await build_board(session, user, ["Todo", "Doing"])
    made = await fill(session, user, todo.id, ["a", "b"])

    await cards.move_card(session, user, made[0].id, doing.id, 0)
    await fill(session, user, doing.id, ["z"])

    assert await titles_in(session, doing.id) == ["a", "z"]
    await assert_contiguous(session, doing.id)


async def test_a_card_cannot_be_moved_to_another_board(session, user):
    _first, (todo,) = await build_board(session, user, ["Todo"])
    _second, (elsewhere,) = await build_board(session, user, ["Elsewhere"])
    made = await fill(session, user, todo.id, ["a"])

    with pytest.raises(HTTPException) as raised:
        await cards.move_card(session, user, made[0].id, elsewhere.id, 0)

    assert raised.value.status_code == 400
