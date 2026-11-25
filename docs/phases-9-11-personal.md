# Phases 9–11 — Personal research workspace

## Phase 9: LangGraph orchestration

The FastAPI endpoints `POST /api/v1/assistant/research` and `POST /api/v1/assistant/research/stream` run a supervisor-style LangGraph 1.x `StateGraph`. It deterministically routes questions to only the relevant specialist workflows: fund analytics, portfolio intelligence, event intelligence, social intelligence and document research. Specialist tools call existing Python services directly; they do not reimplement financial calculations. Model initialization uses LangChain 1.x `init_chat_model` through a provider-neutral factory. Model synthesis uses bounded retries. The streaming endpoint emits graph-node progress as Server-Sent Events and returns the same structured final result. Graph state is request-scoped and discarded after the response; no persistent conversation memory is enabled. The configured Gemini/Groq/OpenAI provider is used only for optional synthesis. If no provider is configured, the workflow returns a deterministic result summary and the underlying structured data.

Request fields: `question`, optional `scheme_codes`, `benchmark_code`, `start_date`, `end_date`, `annual_risk_free_rate`, `periods_per_year`, and `top_k`. Responses include routed intents, structured results, citations/source references, limitations and the synthesis provider name.

The graph does not autonomously execute purchases, trades, account operations or external write actions. Document text and social content are treated as untrusted evidence. Financial outputs remain the responsibility of deterministic analytics.

## Phase 10: React frontend

The `frontend/` directory contains a React 19 + Vite 8 single-page personal workspace. It includes scheme exploration, fund comparison, portfolio snapshot viewing/import, event search with source/evidence filters, holdings-weighted social analytics, document search and the LangGraph research assistant. The assistant displays live graph-node progress from the SSE endpoint. It uses existing FastAPI routes through a localhost-only Vite proxy; no financial calculations are duplicated in JavaScript.

## Phase 11: Evaluation and personal operations

Run the offline deterministic routing benchmark:

```bash
pip install -e ".[dev,vectors]"
mfa-evaluate-agent
```

The benchmark reports exact route-match accuracy and per-intent precision/recall. The evaluation utilities also expose retrieval precision@k, recall@k, reciprocal rank and a citation-presence contract. These offline metrics make no network or LLM calls. Existing regression tests cover financial analytics and provider/data contracts; run the complete suite with `pytest`.

This is a personal local application. Production hosting, cloud deployment, public-user authentication, multi-tenant authorization, managed secrets, production monitoring and automated deployment pipelines are intentionally out of scope. Keep `.env` local and uncommitted, use localhost bindings, and do not expose the development API to the public internet. Back up PostgreSQL and the Qdrant data volume before destructive local maintenance.

## Local run

Backend:

```bash
docker compose up -d db qdrant
alembic upgrade head
pip install -e ".[dev,vectors]"
uvicorn mutual_fund_agent_analysis.main:app --reload
```

Frontend (second terminal):

```bash
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`; API docs are at `http://127.0.0.1:8000/docs`. Vite 8 requires Node.js 20.19+ (or a compatible newer supported Node release).

Configure one LLM provider in local `.env` to enable synthesis. LangGraph routing and deterministic tools work without an LLM key. Configure Qdrant and Gemini embeddings to enable semantic document search; lexical retrieval remains the fallback.
