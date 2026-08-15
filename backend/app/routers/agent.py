"""The chat endpoint.

POST, never GET. `csrf.py` records the rule this follows: a GET that mutates is
reachable from an <img> tag on any site in the world, so no agent tool may run on
one. This handler changes the database, so it is a POST and carries the CSRF
header like every other write in the application.

The board is taken from the URL and its ownership is checked here, before the
model is called at all. That ordering matters twice: an unauthorised caller never
causes a billable request, and the board id the tools are bound to has already
been proved to belong to the caller by the time the model can influence anything.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.agent.model import ModelClient, ModelError, OpenRouterClient
from app.agent.runner import run_turn
from app.agent.tools import ToolContext
from app.config import AGENT_RATE_LIMIT, settings
from app.deps import CurrentUser, SessionDep
from app.limiter import limiter
from app.schemas import AgentChatRequest, AgentChatResponse
from app.services.boards import get_owned_board

router = APIRouter(prefix="/api", tags=["agent"])

NOT_CONFIGURED = (
    "The assistant is not configured on this server. "
    "OPENROUTER_API_KEY is not set."
)


def get_model_client() -> ModelClient:
    """The model client, or a 503 saying why there is not one.

    A missing key is a configuration state the application is expected to run in:
    everything phases 0 to 2 built works without it, and the test suite never
    calls a real model. So it fails closed on this one endpoint and says what is
    wrong, rather than refusing to start the process for everybody.

    It is a dependency rather than a module-level object so the tests can
    substitute a fake and drive the whole loop with no network and no spend.
    """
    # Falsy rather than "is None". The validator on Settings already turns a
    # blank environment variable into None at construction, but this is the check
    # that has to fail closed, and it should not depend on a normalisation
    # happening somewhere else to do it.
    if not settings.openrouter_api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, detail=NOT_CONFIGURED
        )
    return OpenRouterClient(settings.openrouter_api_key)


ModelClientDep = Annotated[ModelClient, Depends(get_model_client)]


@router.post("/boards/{board_id}/agent/chat", response_model=AgentChatResponse)
@limiter.limit(AGENT_RATE_LIMIT)
async def chat(
    board_id: uuid.UUID,
    body: AgentChatRequest,
    request: Request,
    session: SessionDep,
    user: CurrentUser,
    client: ModelClientDep,
):
    board = await get_owned_board(session, user, board_id)

    ctx = ToolContext(session=session, user=user, board_id=board.id)

    try:
        return await run_turn(client, ctx, body.message)
    except ModelError as exc:
        # 502: this application is working and something upstream is not. The
        # message is one of ModelError's own fixed sentences, never an upstream
        # body, which can echo the request and with it the board's contents.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
