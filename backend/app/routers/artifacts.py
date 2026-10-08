from fastapi import APIRouter, HTTPException, Request, Response

from ..artifacts import get_artifact

router = APIRouter()


@router.get("/artifacts/{artifact_id}")
async def get_artifact_route(artifact_id: str, request: Request) -> Response:
    runtime = request.app.state.runtime
    item = get_artifact(runtime.artifacts, artifact_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Artifact not found or expired")
    data, content_type = item
    return Response(content=data, media_type=content_type)
