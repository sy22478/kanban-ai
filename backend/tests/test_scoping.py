"""Ownership scoping.

Phase 1 has no login, so this is not yet an auth test. It tests the layer that
phase 2's auth will sit on top of: that every lookup is filtered by owner, using
real ids belonging to another user rather than made-up ones.

A test that only ever asks for its own data proves nothing. Every id used here is
fetched from the other user's real rows first.
"""

import pytest
from fastapi import HTTPException

from app.services import boards, cards, columns


async def board_with_a_card(session, owner):
    board = await boards.create_board(session, owner, "Private")
    column = await columns.create_column(session, owner, board.id, "Todo")
    card = await cards.create_card(session, owner, column.id, "secret", None)
    return board, column, card


async def test_another_users_board_is_not_listed(session, user, other_user):
    await board_with_a_card(session, other_user)
    await boards.create_board(session, user, "Mine")

    visible = await boards.list_boards(session, user)

    assert [board.title for board in visible] == ["Mine"]


async def test_another_users_board_is_404_not_403(session, user, other_user):
    board, _column, _card = await board_with_a_card(session, other_user)

    with pytest.raises(HTTPException) as raised:
        await boards.get_owned_board(session, user, board.id)

    # 404 and not 403: a 403 would confirm the board exists.
    assert raised.value.status_code == 404


async def test_another_users_column_is_404(session, user, other_user):
    _board, column, _card = await board_with_a_card(session, other_user)

    with pytest.raises(HTTPException) as raised:
        await columns.get_owned_column(session, user, column.id)

    assert raised.value.status_code == 404


async def test_another_users_card_is_404(session, user, other_user):
    _board, _column, card = await board_with_a_card(session, other_user)

    with pytest.raises(HTTPException) as raised:
        await cards.get_owned_card(session, user, card.id)

    assert raised.value.status_code == 404


async def test_another_users_board_cannot_be_renamed(session, user, other_user):
    board, _column, _card = await board_with_a_card(session, other_user)

    with pytest.raises(HTTPException) as raised:
        await boards.rename_board(session, user, board.id, "taken over")

    assert raised.value.status_code == 404

    untouched = await boards.get_owned_board(session, other_user, board.id)
    assert untouched.title == "Private"


async def test_another_users_board_cannot_be_deleted(session, user, other_user):
    board, _column, _card = await board_with_a_card(session, other_user)

    with pytest.raises(HTTPException) as raised:
        await boards.delete_board(session, user, board.id)

    assert raised.value.status_code == 404
    assert await boards.get_owned_board(session, other_user, board.id) is not None


async def test_a_card_cannot_be_moved_into_another_users_column(
    session, user, other_user
):
    _their_board, their_column, _their_card = await board_with_a_card(
        session, other_user
    )
    my_board = await boards.create_board(session, user, "Mine")
    my_column = await columns.create_column(session, user, my_board.id, "Todo")
    my_card = await cards.create_card(session, user, my_column.id, "mine", None)

    with pytest.raises(HTTPException) as raised:
        await cards.move_card(session, user, my_card.id, their_column.id, 0)

    assert raised.value.status_code == 404

    still_mine = await cards.get_owned_card(session, user, my_card.id)
    assert still_mine.column_id == my_column.id
