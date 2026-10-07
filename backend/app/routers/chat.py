"""
PHASE 1 TEMPORARY ENDPOINT -- non-streaming, synchronous request/response.

Exists only to validate the agent graph, tools, checkpointer, and store are
wired up correctly before Phase 2 replaces this with the real
EventSourceResponse-based `/api/chat/stream` SSE endpoint.
"""

from fastapi import APIRouter, Request
from langchain_core.messages import HumanMessage

from ..schemas import ChatRequest

router = APIRouter()


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> dict:
    graph = request.app.state.graph
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=req.message)]},
        config={"configurable": {"thread_id": req.thread_id}},
    )
    final_message = result["messages"][-1]
    return {"reply": final_message.content}
