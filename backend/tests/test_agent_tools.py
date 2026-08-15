"""The agent's tool layer, exercised without a model anywhere near it.

The point of these tests is that the scoping holds as a property of the code
rather than as a property of whatever the model was persuaded to emit. Every
refusal below is driven by handing the dispatcher exactly the arguments a
successfully injected model would produce: a real id, belonging to somebody
else, or to another of the caller's own boards.
"""

import uuid

import pytest
from sqlalchemy import select

from app.agent.tools import TOOLS, ToolContext, dispatch, tool_definitions
from app.models import Card
from app.services import boards, cards, columns


async def build_board(session, user, title="Board"):
    """A board with one column and one card, through the real services."""
    board = await boards.create_board(session, user, title)
    column = await columns.create_column(session, user, board.id, "To Do")
    card = await cards.create_card(session, user, column.id, "Write the tests", None)
    return board, column, card


@pytest.fixture
async def owned(session, user):
    return await build_board(session, user, "Owner board")


@pytest.fixture
async def foreign(session, other_user):
    """A board belonging to the second tenant."""
    return await build_board(session, other_user, "Mallory board")


def context(session, user, board):
    return ToolContext(session=session, user=user, board_id=board.id)


async def count_cards(session) -> int:
    return len((await session.execute(select(Card))).scalars().all())


class TestTheToolsWork:
    async def test_list_board_returns_columns_and_cards(self, session, user, owned):
        board, column, card = owned
        result = await dispatch(context(session, user, board), "list_board", {})

        assert result.ok
        assert result.mutated is False
        assert result.content["board_title"] == "Owner board"
        [listed_column] = result.content["columns"]
        assert listed_column["column_id"] == str(column.id)
        [listed_card] = listed_column["cards"]
        assert listed_card["card_id"] == str(card.id)
        assert listed_card["title"] == "Write the tests"

    async def test_create_card_adds_one(self, session, user, owned):
        board, column, _card = owned
        result = await dispatch(
            context(session, user, board),
            "create_card",
            {"column_id": str(column.id), "title": "New card"},
        )

        assert result.ok
        assert result.mutated is True
        assert result.content["title"] == "New card"
        # Appended after the fixture's card rather than landing on top of it.
        assert result.content["position"] == 1
        assert await count_cards(session) == 2

    async def test_edit_card_changes_the_title(self, session, user, owned):
        board, _column, card = owned
        result = await dispatch(
            context(session, user, board),
            "edit_card",
            {"card_id": str(card.id), "title": "Renamed"},
        )

        assert result.ok
        assert result.content["title"] == "Renamed"

    async def test_edit_card_leaves_an_omitted_description_alone(
        self, session, user, owned
    ):
        """Omitting a field and clearing it are different requests.

        The service takes description_provided for exactly this reason, and the
        tool has to work out the same distinction from the model's arguments.
        """
        board, column, _card = owned
        card = await cards.create_card(
            session, user, column.id, "Has a description", "keep me"
        )

        result = await dispatch(
            context(session, user, board),
            "edit_card",
            {"card_id": str(card.id), "title": "Retitled"},
        )

        assert result.ok
        assert result.content["description"] == "keep me"

    async def test_edit_card_clears_an_explicit_null_description(
        self, session, user, owned
    ):
        board, column, _card = owned
        card = await cards.create_card(
            session, user, column.id, "Has a description", "remove me"
        )

        result = await dispatch(
            context(session, user, board),
            "edit_card",
            {"card_id": str(card.id), "description": None},
        )

        assert result.ok
        assert result.content["description"] is None

    async def test_move_card_to_another_column(self, session, user, owned):
        board, _column, card = owned
        target = await columns.create_column(session, user, board.id, "Done")

        result = await dispatch(
            context(session, user, board),
            "move_card",
            {
                "card_id": str(card.id),
                "column_id": str(target.id),
                "position": 0,
            },
        )

        assert result.ok
        assert result.content["column_id"] == str(target.id)
        assert result.content["position"] == 0

    async def test_delete_card_removes_it(self, session, user, owned):
        board, _column, card = owned
        result = await dispatch(
            context(session, user, board),
            "delete_card",
            {"card_id": str(card.id)},
        )

        assert result.ok
        assert result.mutated is True
        assert result.content["title"] == "Write the tests"
        assert await count_cards(session) == 0


class TestMalformedCalls:
    """A bad call is answered, not raised, and never half-applied."""

    async def test_unknown_tool_is_refused(self, session, user, owned):
        board, _column, _card = owned
        result = await dispatch(
            context(session, user, board), "drop_database", {"table": "users"}
        )

        assert result.ok is False
        assert result.mutated is False
        assert "drop_database" in result.content["error"]

    async def test_missing_argument_is_refused(self, session, user, owned):
        board, column, _card = owned
        result = await dispatch(
            context(session, user, board),
            "create_card",
            {"column_id": str(column.id)},
        )

        assert result.ok is False
        assert await count_cards(session) == 1

    async def test_unexpected_argument_is_refused(self, session, user, owned):
        """extra="forbid", so a call that smuggles a field is not silently trimmed.

        owner_id is the field an injected model would most want to add. It is not
        that the tool would honour it -- no tool reads one -- it is that a call
        carrying it is not the call the schema describes, and answering it as
        valid would mean the dispatcher and the advertised schema disagree.
        """
        board, column, _card = owned
        result = await dispatch(
            context(session, user, board),
            "create_card",
            {
                "column_id": str(column.id),
                "title": "Sneaky",
                "owner_id": str(uuid.uuid4()),
            },
        )

        assert result.ok is False
        assert await count_cards(session) == 1

    async def test_empty_title_is_refused(self, session, user, owned):
        board, column, _card = owned
        result = await dispatch(
            context(session, user, board),
            "create_card",
            {"column_id": str(column.id), "title": ""},
        )

        assert result.ok is False
        assert await count_cards(session) == 1

    async def test_negative_position_is_refused(self, session, user, owned):
        board, _column, card = owned
        result = await dispatch(
            context(session, user, board),
            "move_card",
            {
                "card_id": str(card.id),
                "column_id": str(card.column_id),
                "position": -1,
            },
        )

        assert result.ok is False

    async def test_a_card_id_that_is_not_a_uuid_is_refused(self, session, user, owned):
        board, _column, _card = owned
        result = await dispatch(
            context(session, user, board),
            "delete_card",
            {"card_id": "the one about auth"},
        )

        assert result.ok is False
        assert await count_cards(session) == 1

    async def test_a_nonexistent_card_is_not_found(self, session, user, owned):
        board, _column, _card = owned
        result = await dispatch(
            context(session, user, board),
            "delete_card",
            {"card_id": str(uuid.uuid4())},
        )

        assert result.ok is False
        assert result.content["error"] == "Card not found"


class TestTenantIsolation:
    """The caller's ids are the only ones that resolve.

    Each test hands the dispatcher a real id owned by the other tenant, which is
    precisely what a model talked into acting on someone else's board would
    emit. The refusal comes from the ownership join, not from the model
    declining.
    """

    async def test_listing_refuses_a_board_owned_by_someone_else(
        self, session, user, foreign
    ):
        foreign_board, _column, _card = foreign
        result = await dispatch(context(session, user, foreign_board), "list_board", {})

        assert result.ok is False
        assert result.content["error"] == "Board not found"

    async def test_create_refuses_a_foreign_column(
        self, session, user, owned, foreign
    ):
        board, _column, _card = owned
        _foreign_board, foreign_column, _foreign_card = foreign

        result = await dispatch(
            context(session, user, board),
            "create_card",
            {"column_id": str(foreign_column.id), "title": "Planted"},
        )

        assert result.ok is False
        assert result.content["error"] == "Column not found"
        # The card was not created anywhere, least of all on Mallory's board.
        assert await count_cards(session) == 2

    async def test_edit_refuses_a_foreign_card(self, session, user, owned, foreign):
        board, _column, _card = owned
        _foreign_board, _foreign_column, foreign_card = foreign

        result = await dispatch(
            context(session, user, board),
            "edit_card",
            {"card_id": str(foreign_card.id), "title": "Owned by me now"},
        )

        assert result.ok is False
        assert result.content["error"] == "Card not found"
        await session.refresh(foreign_card)
        assert foreign_card.title == "Write the tests"

    async def test_move_refuses_a_foreign_card(self, session, user, owned, foreign):
        board, column, _card = owned
        _foreign_board, _foreign_column, foreign_card = foreign

        result = await dispatch(
            context(session, user, board),
            "move_card",
            {
                "card_id": str(foreign_card.id),
                "column_id": str(column.id),
                "position": 0,
            },
        )

        assert result.ok is False
        assert result.content["error"] == "Card not found"
        await session.refresh(foreign_card)
        assert foreign_card.column_id != column.id

    async def test_move_refuses_a_foreign_target_column(
        self, session, user, owned, foreign
    ):
        board, _column, card = owned
        _foreign_board, foreign_column, _foreign_card = foreign

        result = await dispatch(
            context(session, user, board),
            "move_card",
            {
                "card_id": str(card.id),
                "column_id": str(foreign_column.id),
                "position": 0,
            },
        )

        assert result.ok is False
        await session.refresh(card)
        assert card.column_id != foreign_column.id

    async def test_delete_refuses_a_foreign_card(self, session, user, owned, foreign):
        board, _column, _card = owned
        _foreign_board, _foreign_column, foreign_card = foreign

        result = await dispatch(
            context(session, user, board),
            "delete_card",
            {"card_id": str(foreign_card.id)},
        )

        assert result.ok is False
        assert result.content["error"] == "Card not found"
        assert await count_cards(session) == 2


class TestTheBoardBinding:
    """The agent is confined to the board the chat is bound to.

    This is a narrowing inside one account rather than tenant isolation. Both
    boards below belong to the same user, so nothing here is about reaching
    another tenant; it is about the blast radius of an injection being one board
    instead of everything the caller owns.
    """

    async def test_create_refuses_a_column_on_another_of_my_boards(
        self, session, user, owned
    ):
        board, _column, _card = owned
        other_board, other_column, _other_card = await build_board(
            session, user, "My other board"
        )

        result = await dispatch(
            context(session, user, board),
            "create_card",
            {"column_id": str(other_column.id), "title": "Wrong board"},
        )

        assert result.ok is False
        assert result.content["error"] == "Column not found"

    async def test_delete_refuses_a_card_on_another_of_my_boards(
        self, session, user, owned
    ):
        board, _column, _card = owned
        _other_board, _other_column, other_card = await build_board(
            session, user, "My other board"
        )

        result = await dispatch(
            context(session, user, board),
            "delete_card",
            {"card_id": str(other_card.id)},
        )

        assert result.ok is False
        assert result.content["error"] == "Card not found"
        assert await count_cards(session) == 2

    async def test_edit_refuses_a_card_on_another_of_my_boards(
        self, session, user, owned
    ):
        board, _column, _card = owned
        _other_board, _other_column, other_card = await build_board(
            session, user, "My other board"
        )

        result = await dispatch(
            context(session, user, board),
            "edit_card",
            {"card_id": str(other_card.id), "title": "Reached across"},
        )

        assert result.ok is False
        assert result.content["error"] == "Card not found"
        await session.refresh(other_card)
        assert other_card.title == "Write the tests"

    async def test_move_refuses_a_card_on_another_of_my_boards(
        self, session, user, owned
    ):
        board, column, _card = owned
        _other_board, _other_column, other_card = await build_board(
            session, user, "My other board"
        )

        result = await dispatch(
            context(session, user, board),
            "move_card",
            {
                "card_id": str(other_card.id),
                "column_id": str(column.id),
                "position": 0,
            },
        )

        assert result.ok is False
        assert result.content["error"] == "Card not found"
        await session.refresh(other_card)
        assert other_card.column_id != column.id

    async def test_move_refuses_a_target_column_on_another_of_my_boards(
        self, session, user, owned
    ):
        """Refused as not found, rather than as a cross-board move.

        move_card's own guard would also stop this, with 400 "A card cannot be
        moved to a different board". That answer confirms the column exists and
        is the caller's. The binding check runs first so the agent gets the same
        uniform 404 it gets for anything else off this board.
        """
        board, _column, card = owned
        _other_board, other_column, _other_card = await build_board(
            session, user, "My other board"
        )

        result = await dispatch(
            context(session, user, board),
            "move_card",
            {
                "card_id": str(card.id),
                "column_id": str(other_column.id),
                "position": 0,
            },
        )

        assert result.ok is False
        assert result.content["error"] == "Column not found"
        await session.refresh(card)
        assert card.column_id != other_column.id


class TestToolDefinitions:
    def test_every_tool_is_advertised(self):
        names = {d["function"]["name"] for d in tool_definitions()}
        assert names == set(TOOLS)
        assert names == {
            "list_board",
            "create_card",
            "edit_card",
            "move_card",
            "delete_card",
        }

    def test_no_tool_takes_a_user_or_board_argument(self):
        """The scoping property, asserted rather than described.

        If someone later adds a user_id or board_id parameter to a tool so the
        model can "say which board", this goes red. That parameter is the whole
        attack: it turns an id in a card's text into an id the agent will act on.
        """
        for definition in tool_definitions():
            properties = definition["function"]["parameters"].get("properties", {})
            assert "user_id" not in properties
            assert "owner_id" not in properties
            assert "board_id" not in properties

    def test_the_advertised_schema_is_the_validated_one(self):
        """One source of truth for each tool's arguments.

        Hand-written JSON schemas beside Pydantic models drift, and the failure
        is silent: the model is told about a field the dispatcher forbids.
        """
        for definition in tool_definitions():
            spec = TOOLS[definition["function"]["name"]]
            expected = spec.args_model.model_json_schema()
            expected.pop("title", None)
            assert definition["function"]["parameters"] == expected
