"""Personal research assistant endpoints."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from mutual_fund_agent_analysis.agents.research_graph import build_research_graph
from mutual_fund_agent_analysis.api.schemas.assistant import ResearchAssistantRequest
from mutual_fund_agent_analysis.database.session import get_db

router = APIRouter(prefix="/assistant", tags=["research-assistant"])
logger = logging.getLogger(__name__)


@router.get("/capabilities")
def assistant_capabilities() -> dict[str, Any]:
    return {
        "orchestration": "LangGraph",
        "agents": ["fund_research", "portfolio_intelligence", "news_event", "social_intelligence", "document_research"],
        "llm_synthesis": "optional; configured provider required",
        "financial_calculations": "deterministic analytics services",
        "supported_providers": ["gemini", "groq", "openai"],
    }


@router.post("/research")
def run_research(
    request: ResearchAssistantRequest,
    session: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    try:
        graph = build_research_graph()
        result = graph.invoke({"request": request, "session": session})
        return jsonable_encoder({
            "question": request.question,
            "intents": result.get("intents", []),
            "answer": result.get("answer", "No answer generated."),
            "results": result.get("results", {}),
            "citations": result.get("citations", []),
            "errors": result.get("errors", []),
            "model_used": result.get("model_used"),
        })
    except Exception as exc:
        logger.exception("Research workflow execution failed.")
        raise HTTPException(status_code=500, detail="Research workflow failed. Check local API logs.") from exc
