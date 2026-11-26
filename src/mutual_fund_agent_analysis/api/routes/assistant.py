"""Personal research assistant endpoints."""

import json
import logging
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.agents.research_graph import build_research_graph
from mutual_fund_agent_analysis.api.schemas.assistant import ResearchAssistantRequest
from mutual_fund_agent_analysis.database.session import get_db

router = APIRouter(prefix="/assistant", tags=["research-assistant"])
logger = logging.getLogger(__name__)


CAPABILITY_REGISTRY = {
    "fund": "Scheme discovery, performance, risk, returns and multi-fund comparison.",
    "category": (
        "Exact-cohort category peers, common observation windows and comparable return bases."
    ),
    "portfolio": ("Dated AMC holdings, sector allocation, concentration and portfolio overlap."),
    "actual_exposure": (
        "Ledger-derived units, reconciled NAV valuation, "
        "redemption-aware exposure and XIRR context."
    ),
    "security": (
        "Underlying equity quotes, dated fundamentals, "
        "corporate observations and source provenance."
    ),
    "events": (
        "Source-attributed events, publication/effective dates, "
        "corrections and historical exposure."
    ),
    "social": "Permitted Reddit/X collection, retention-aware discussion volume and sentiment.",
    "documents": "Lexical and optional Qdrant retrieval with document/chunk citations.",
}


@router.get("/capabilities")
def assistant_capabilities() -> dict[str, Any]:
    """Return the capability registry used by the API and frontend Overview."""
    return {
        "orchestration": "LangGraph",
        "langgraph_runtime": "1.x; step updates via Server-Sent Events",
        "langchain_model_api": "init_chat_model",
        "agents": list(CAPABILITY_REGISTRY),
        "capabilities": [
            {"id": capability_id, "description": description}
            for capability_id, description in CAPABILITY_REGISTRY.items()
        ],
        "llm_synthesis": "optional; configured provider required",
        "financial_calculations": "deterministic analytics services",
        "supported_providers": ["gemini", "groq", "openai"],
        "streaming_endpoint": "/api/v1/assistant/research/stream",
    }


def _sse(event: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(jsonable_encoder(payload), ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {encoded}\n\n"


@router.post("/research/stream")
def stream_research(
    request: ResearchAssistantRequest,
    session: Annotated[Session, Depends(get_db)],
    http_request: Request,
) -> StreamingResponse:
    """Stream LangGraph node progress and the final grounded research result."""
    research_run_id = uuid4().hex

    def events():
        graph = build_research_graph()
        final_state: dict[str, Any] = {}
        try:
            for update in graph.stream(
                {"request": request, "session": session, "research_run_id": research_run_id},
                stream_mode="updates",
            ):
                for node, output in update.items():
                    final_state.update(output)
                    events_by_node = {
                        "plan": "Intent classification complete.",
                        "specialist_agents": "Deterministic research tools complete.",
                        "synthesize": "Research synthesis complete.",
                    }
                    yield _sse(
                        "progress",
                        {
                            "node": node,
                            "research_run_id": research_run_id,
                            "message": events_by_node.get(node, f"{node} complete."),
                            "intents": final_state.get("intents", []),
                        },
                    )
            yield _sse(
                "complete",
                {
                    "question": request.question,
                    "research_run_id": research_run_id,
                    "intents": final_state.get("intents", []),
                    "answer": final_state.get("answer", "No answer generated."),
                    "results": final_state.get("results", {}),
                    "citations": final_state.get("citations", []),
                    "errors": final_state.get("errors", []),
                    "model_used": final_state.get("model_used"),
                },
            )
        except Exception:
            logger.exception("Streaming research workflow failed.")
            yield _sse(
                "error",
                {"detail": "Research workflow failed. Check local API logs."},
            )

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
            "X-Research-Run-ID": research_run_id,
        },
    )


@router.post("/research")
def run_research(
    request: ResearchAssistantRequest,
    session: Annotated[Session, Depends(get_db)],
    http_request: Request,
) -> dict[str, Any]:
    research_run_id = uuid4().hex
    try:
        graph = build_research_graph()
        result = graph.invoke(
            {"request": request, "session": session, "research_run_id": research_run_id}
        )
        return jsonable_encoder(
            {
                "question": request.question,
                "research_run_id": research_run_id,
                "intents": result.get("intents", []),
                "answer": result.get("answer", "No answer generated."),
                "results": result.get("results", {}),
                "citations": result.get("citations", []),
                "errors": result.get("errors", []),
                "model_used": result.get("model_used"),
            }
        )
    except Exception as exc:
        logger.exception("Research workflow execution failed.")
        raise HTTPException(
            status_code=500, detail="Research workflow failed. Check local API logs."
        ) from exc
