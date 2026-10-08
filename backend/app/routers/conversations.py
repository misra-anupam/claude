from fastapi import APIRouter, Request

from ..config import settings
from ..conversations import get_conversation_messages, list_conversations

router = APIRouter()


@router.get("/conversations")
async def list_conversations_route() -> list[dict]:
    return await list_conversations(settings.database_url)


@router.get("/conversations/{thread_id}/messages")
async def get_conversation_messages_route(thread_id: str, request: Request) -> list[dict]:
    runtime = request.app.state.runtime
    return await get_conversation_messages(runtime.checkpointer, thread_id)
