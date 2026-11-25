# Mutual Fund Agent Analysis

An AI-powered mutual fund research and market-intelligence platform focused initially on **Indian mutual funds**. The project combines quantitative fund analytics, multi-fund comparison, portfolio intelligence, financial-document research, social sentiment, and upcoming-news monitoring.

> **Project status:** The local-first core (NAV/benchmark ingestion, deterministic analytics, investor ledger, portfolio/evidence foundations, LangGraph and React workspace) is implemented. Financial-reliability extensions for Phases 0–7 are being delivered in a dedicated branch; authoritative IDCW coverage, AMC-specific file adapters and live provider verification remain source-dependent gates. This is a personal local application, not a public deployment. See `docs/roadmap-financial-reliability.md` and `docs/phase-0-7-reliability-implementation.md`.

## Table of Contents

- [Vision](#vision)
- [Core Capabilities](#core-capabilities)
- [Time-Based Analysis](#time-based-analysis)
- [Multi-Fund Comparison](#multi-fund-comparison)
- [Portfolio and Stock Intelligence](#portfolio-and-stock-intelligence)
- [Social Media and Sentiment Intelligence](#social-media-and-sentiment-intelligence)
- [News and Upcoming Events](#news-and-upcoming-events)
- [AI Agent Architecture](#ai-agent-architecture)
- [Technology Stack](#technology-stack)
- [Data Sources and Integrations](#data-sources-and-integrations)
- [Quantitative Analytics](#quantitative-analytics)
- [Data and System Architecture](#data-and-system-architecture)
- [Development Roadmap](#development-roadmap)
- [Evaluation and Reliability](#evaluation-and-reliability)
- [Configuration](#configuration)
- [Responsible Use and Data Limitations](#responsible-use-and-data-limitations)

## Vision

Build a research workspace where a user can:

1. Explore an Indian mutual fund and inspect its historical performance.
2. Analyze a fund at daily, weekly, monthly, quarterly, yearly, or custom frequency and date range, subject to available source data.
3. Compare multiple funds side by side over the same dates and frequency.
4. Examine risk, consistency, benchmark-relative performance, holdings, sector exposure, and portfolio overlap.
5. Run historical SIP and lump-sum investment simulations.
6. Investigate public discussions about the stocks held by a fund on Reddit and X (Twitter).
7. Monitor company announcements, financial news, upcoming corporate events, and circulating but unverified claims.
8. Ask an AI research assistant to synthesize quantitative results and sourced information into an explainable report.

The system is intended for personal research and education. It is not designed to execute trades or guarantee future performance.

## Core Capabilities

| Module | Purpose |
|---|---|
| Fund Explorer | Search schemes, identify categories, and inspect scheme metadata |
| Single Fund Analysis | Study one fund's performance, risk, and historical behaviour |
| Comparison Studio | Compare several funds across common periods and metrics |
| Risk & Performance Lab | Calculate financial metrics and rolling statistics |
| Portfolio Intelligence | Analyze holdings, sector exposure, concentration, and overlap |
| SIP & Investment Simulator | Backtest historical contributions and model hypothetical scenarios |
| Social Intelligence | Analyze relevant Reddit and X discussions about funds, companies, and sectors |
| News & Event Radar | Track reported news, official announcements, and scheduled events |
| Document Intelligence | Search factsheets, scheme documents, and portfolio disclosures using RAG |
| AI Research Assistant | Route questions to relevant tools and synthesize evidence-backed findings |

## Time-Based Analysis

Time frequency and analysis duration are separate controls.

### Supported observation frequencies

- **Daily:** Use available published NAV observations and daily returns.
- **Weekly:** Aggregate to the last available observation in each week.
- **Monthly:** Use the last available observation in each month.
- **Quarterly:** Use the last available observation in each quarter.
- **Yearly:** Support calendar-year observations and calendar-year returns.

### Supported analysis windows

- Preset lookbacks such as 1 month, 3 months, 6 months, 1 year, 3 years, and 5 years.
- Maximum available history.
- User-defined start and end dates.

For example, a user may request **monthly observations over five years** or **daily observations over three months**.

The application must use actual available observations. Mutual fund NAV is generally published on business days, not every calendar day. Weekends and holidays must not be represented as fabricated NAV observations. For period boundaries, use a documented rule (for example, the latest valid NAV on or before the requested boundary) and expose the actual observation dates used. Missing observations must not be silently forward-filled for return calculations.

**Keep frequency separate from lookback duration.** "Monthly observations over five years" is not the same as "five-year return." Calendar-year returns should use the last available NAV in each calendar year and the preceding year-end NAV. A trailing one-year return should use the selected end date and the corresponding observation around one year earlier.

## Multi-Fund Comparison

Users should be able to select multiple schemes and compare them side by side.

### Comparison controls

- Scheme selection and removal.
- Common start and end dates.
- Daily, weekly, monthly, quarterly, or yearly frequency.
- Scheme, plan, and option identification (including Direct / Regular and Growth / IDCW).
- Metric selection.
- A consistent total-return methodology for IDCW options; raw NAV change alone is not a fair total-return comparison when distributions have been paid.
- Benchmark selection where a suitable benchmark is available.
- Exportable tables and charts.

### Comparison outputs

- Absolute and annualized returns.
- Calendar-year and trailing-period returns.
- Rolling returns and rolling consistency.
- Volatility and downside risk.
- Sharpe and Sortino ratios.
- Alpha, beta, and tracking measures where appropriate.
- Maximum drawdown and recovery.
- Expense ratio and available fund metadata.
- Portfolio allocation and holdings overlap.
- Social and news signals for underlying holdings.

### Comparison visualizations

- Normalized growth chart (common starting value, e.g. 100).
- Cumulative return chart.
- Drawdown chart.
- Rolling-return chart.
- Risk-versus-return plot.
- Metric comparison table with sorting and highlighting.

Raw NAV values must not be compared directly across schemes because their starting NAV levels differ. Comparisons must align observations to a common date range and disclose missing observations. Compare like with like: identify the same scheme category, plan type, option, and relevant benchmark. For IDCW options, use a defensible total-return series that accounts for distributions and reinvestment assumptions; do not compare raw IDCW NAV returns with Growth-option returns as though they were equivalent. Benchmarks should use suitable Total Return Index (TRI) data when available; price-index comparisons omit reinvested dividends. If a comparable TRI series is unavailable, disclose that limitation.

## Portfolio and Stock Intelligence

Where reliable portfolio disclosures are available, the platform should:

- Retrieve and parse monthly fund holdings.
- Identify the underlying listed companies and securities.
- Calculate stock and sector exposure.
- Identify top holdings and concentration.
- Calculate portfolio concentration measures such as HHI.
- Compare holdings between funds and estimate portfolio overlap.
- Track changes in holdings and weights between disclosure periods.
- Link each holding to relevant market news and social discussions.

Portfolio analysis must retain the disclosure's effective date. A current portfolio must not be used as a substitute for historical holdings.

## Social Media and Sentiment Intelligence

The platform should analyze public discussions on **Reddit** and **X (Twitter)** about:

- Stocks held by selected mutual funds.
- Mutual fund schemes, AMCs, and fund managers.
- Relevant sectors and market themes.
- Company results, management changes, corporate actions, and other events.

### Collection and analysis

- Collect posts and comments through permitted platform APIs or approved data providers.
- Resolve company names, ticker symbols, aliases, and ambiguous mentions.
- Classify sentiment as positive, negative, or neutral.
- Extract topics, entities, claims, and event references.
- Identify bullish and bearish arguments.
- Measure discussion volume and engagement over time.
- Detect sudden changes in discussion volume or sentiment.
- Compare Reddit and X signals.
- Identify duplicate, spam-like, promotional, or potentially coordinated content where evidence permits.
- Preserve links and source timestamps for traceability.

### Social analytics

- Sentiment distribution and weighted sentiment score.
- Daily, weekly, monthly, and yearly sentiment trends where data coverage permits.
- Discussion volume and engagement trends.
- Sentiment momentum and volatility.
- Topic frequency and emerging themes.
- Reddit-versus-X divergence.
- Stock-level sentiment and portfolio-exposure-weighted fund-level sentiment.

A fund-level social sentiment measure may be calculated as a weighted aggregation of stock-level signals using the relevant portfolio weights. It must be labelled as an experimental indicator, disclose coverage and missing holdings, and never be presented as a measure of the fund's actual NAV or intrinsic value. The calculation should use holdings effective for the relevant period, not current holdings applied retrospectively. Distinguish the volume of discussion from sentiment, and avoid treating likes, reposts, or upvotes as proof that a claim is credible.

Historical sentiment analysis is limited by the historical data accessible through each provider and by the date collection began.

## News and Upcoming Events

The News & Event Radar should distinguish between what has happened, what is officially scheduled, what has been reported, and what is merely circulating. The system cannot know future news before it is published; it can monitor scheduled events, developing stories, and public claims that are already circulating.

### Event and news categories

- Official company announcements and exchange filings.
- Scheduled board meetings and financial-result announcements.
- Dividends, record dates, splits, bonuses, and other corporate actions.
- Mergers, acquisitions, fundraising, and management changes.
- Regulatory and policy developments.
- Sector-level events and macroeconomic announcements.
- Financial news and analyst commentary.
- Rumours, speculation, and unverified social-media claims.

### Event status labels

Every item should have an explicit status, such as:

- **Confirmed:** Supported by an official filing or primary source.
- **Scheduled:** An event date is officially published.
- **Reported:** Covered by an identifiable news source but not independently confirmed.
- **Unverified:** Circulating claim without sufficient confirmation.
- **Speculative:** Opinion or expectation rather than an established fact.
- **Disproved / Outdated:** Contradicted, withdrawn, or superseded by newer information.

### News-to-portfolio mapping

For every relevant item, the platform should identify:

1. The company, sector, or fund to which it relates.
2. Whether the company is present in a selected fund's disclosed holdings.
3. The portfolio weight and holdings disclosure date, if available.
4. The event date, publication time, and source.
5. The confirmation status and supporting evidence.
6. Relevant Reddit and X discussion, kept separate from verified facts.
7. Historical context and possible areas of exposure, without claiming a certain market impact.

The application should support watchlists and scheduled monitoring so users can follow selected funds and their underlying holdings.

## AI Agent Architecture

Use **LangGraph** for orchestration and **LangChain** for model and tool integrations. A supervisor routes each request to the minimum set of specialist agents required.

### Proposed agents

| Agent / component | Responsibilities |
|---|---|
| Supervisor / Router | Understand intent, plan tasks, route work, and manage shared state |
| Fund Research Agent | Coordinate scheme discovery and call performance, risk, comparison, and SIP tools |
| Portfolio Intelligence Agent | Retrieve holdings and coordinate exposure, concentration, and overlap analysis |
| Social Intelligence Agent | Coordinate Reddit/X collection, entity resolution, sentiment, and topic analysis |
| News & Event Agent | Retrieve official filings, scheduled events, news, and developing claims |
| Document Research Agent | Retrieve evidence from factsheets, scheme documents, and disclosures using RAG |
| Research Synthesis Agent | Produce sourced reports from validated quantitative and qualitative outputs |

**These agents call deterministic services; the services are not separate LLM agents.** Implement returns, risk metrics, benchmark alignment, SIP cash flows, portfolio overlap, and sentiment aggregation as ordinary tested Python modules exposed as tools. This avoids unnecessary LLM calls, reduces latency and cost, and makes numerical results reproducible.

Not every request should invoke every agent. A simple CAGR query should call the performance calculation service directly. A multi-fund risk comparison should call the relevant performance and risk services. A complete research request may additionally invoke portfolio, social, news, and document research components.

### LLM responsibilities

- **Groq:** Fast routing, classification, lightweight extraction, and summarization.
- **Google Gemini:** Long-context document analysis, contextual reasoning, and research synthesis.
- **OpenAI (optional):** Alternative provider for selected reasoning or evaluation tasks.

A provider abstraction should allow model changes without rewriting agent logic. Model names and availability should be configured rather than hard-coded throughout the application.

### Deterministic tools first

Financial calculations, date alignment, holdings aggregation, sentiment aggregation, and event-status rules should be implemented as testable Python functions. LLMs should interpret and explain their outputs, not invent numerical results.

## Technology Stack

| Layer | Proposed technology |
|---|---|
| Frontend | React + Vite |
| Backend API | FastAPI |
| Agent orchestration | LangGraph |
| LLM integration | LangChain |
| Fast inference | Groq API |
| Research / long-context model | Google Gemini API |
| Optional model provider | OpenAI API |
| Financial calculations | Pandas, NumPy, SciPy |
| Financial sentiment baseline | FinBERT or another evaluated finance classifier |
| Relational database | PostgreSQL |
| Vector database | Qdrant |
| Embeddings | Gemini embeddings or another supported embedding model |
| Document parsing | PyMuPDF / appropriate HTML and table parsers |
| Visualization | Plotly |
| Search integration | Tavily or another permitted search provider |
| Agent tracing and evaluation | LangSmith |
| Scheduling | APScheduler initially; a task queue if workload requires it |
| Deployment | Docker and Docker Compose |

## Data Sources and Integrations

Potential sources to evaluate:

| Source | Intended use |
|---|---|
| [AMFI](https://www.amfiindia.com/) | Indian mutual fund NAV files and scheme-related information |
| [MFAPI](https://www.mfapi.in/docs/) | Convenient third-party scheme lookup and historical NAV API; validate against official NAV data |
| [SEBI](https://www.sebi.gov.in/) | Regulations, circulars, and official disclosures |
| [NSE India](https://www.nseindia.com/) | Exchange filings, corporate announcements, event information, and benchmark data where accessible |
| [BSE India](https://www.bseindia.com/) | Exchange announcements and corporate filings |
| AMC websites | Factsheets, monthly portfolios, scheme documents, and fund disclosures |
| [Reddit API](https://www.reddit.com/dev/api/) | Permitted public post and comment data |
| [X API](https://docs.x.com/x-api/introduction) | Permitted public post search and engagement data |
| [RBI](https://www.rbi.org.in/) | Monetary policy and macroeconomic information |
| [MOSPI](https://www.mospi.gov.in/) | Official economic statistics |
| News/search providers | Financial news discovery and source retrieval |

AMFI should be treated as the primary reference for mutual fund NAV information; MFAPI is a convenient third-party integration, not the authoritative source. Benchmark TRI history, AMC portfolio disclosures, expense ratios, and scheme metadata require separate acquisition and validation workflows. Exchange websites may provide useful public disclosures but do not necessarily provide a stable, unrestricted API for every dataset.

API availability, access tiers, pricing, rate limits, attribution, retention, and permitted use must be checked before implementation. Do not assume that every source offers a free API or unrestricted historical access. Record the source and effective date for every dataset, and build adapters so that one provider can be replaced without rewriting analytics.

## Quantitative Analytics

### Performance

- Absolute return.
- CAGR.
- XIRR for irregular cash flows.
- Trailing-period returns.
- Calendar-year returns.
- Rolling returns.
- Benchmark excess returns.
- Historical lump-sum and SIP simulations.

### Risk and risk-adjusted performance

- Standard deviation and downside deviation.
- Sharpe ratio and Sortino ratio.
- Beta and alpha, with a clearly defined benchmark and methodology.
- Maximum drawdown and recovery duration.
- Value at Risk (VaR) and Conditional VaR (CVaR).
- Calmar ratio.
- Tracking error and tracking difference where appropriate.

### Portfolio analytics

- Stock and sector exposure.
- Top-holding concentration.
- HHI concentration index.
- Portfolio overlap.
- Holdings and allocation changes.
- Exposure-weighted social and event indicators.

Every metric should document its return convention, observation frequency, annualization convention, risk-free rate (where applicable), benchmark, observation count, date range, and missing-data treatment. Define these conventions centrally and use them consistently across single-fund and multi-fund analysis:

- Calculate returns from an explicitly selected NAV or total-return series; account for distributions when comparing IDCW options.
- Annualize volatility and risk-adjusted ratios using the observation frequency and a documented convention; do not apply a daily annualization factor to monthly returns.
- Calculate Sharpe and Sortino using a dated risk-free-rate series or a clearly disclosed assumption.
- Calculate Alpha and Beta against an appropriate, aligned benchmark return series; document the regression window and frequency.
- State the confidence level, lookback window, and historical or parametric method for VaR/CVaR.
- Distinguish calendar-year returns from trailing-period returns and CAGR.
- Treat insufficient history, missing benchmark observations, and stale data as explicit limitations rather than filling them silently.

## Data and System Architecture

The platform should maintain a clear separation between source ingestion, normalized storage, deterministic analytics, AI orchestration, and presentation.

```text
                  React + Vite
                       |
                    FastAPI
                       |
              LangGraph Supervisor
                       |
        +--------------+----------------+
        |              |                |
  Financial Agents  Social Agents   News / RAG Agents
        |              |                |
        +--------------+----------------+
                       |
              Python Tool Layer
                       |
          +------------+------------+
          |                         |
      PostgreSQL                  Qdrant
  NAV / schemes / holdings    Documents / chunks
  events / social metadata    embeddings / retrieval
          |
    Ingestion Pipelines
          |
  AMFI / MFAPI / AMC / NSE / BSE
  Reddit / X / News / RBI / MOSPI
```

### Data engineering principles

- Store raw provider responses in the append-only `provider_sync_runs` audit table alongside normalized NAV observations, source, fetch time, and observation count.
- Normalize scheme identifiers, company identifiers, dates, currencies, and units.
- Record source, retrieval timestamp, effective date, and publication date.
- Make ingestion jobs idempotent and safe to rerun.
- Deduplicate announcements and social posts.
- Track data coverage and freshness.
- Keep financial time-series data in PostgreSQL, not in the vector database.
- Store document chunks and embeddings in Qdrant with source metadata.
- Retain social content only as permitted by the relevant platform terms and applicable requirements.

## Development Roadmap

Implementation should proceed in working milestones rather than creating all agents and modules at once.

| Phase | Scope | Deliverable |
|---|---|---|
| 1. Foundation and ingestion | Repository setup, configuration, FastAPI, PostgreSQL, NAV reconciliation, benchmark TRI | Reliable application and financial data foundation |
| 2. Deterministic analytics | Returns, rolling metrics, risk, benchmark attribution, drawdown | Tested quantitative calculation library |
| 3. Fund analysis | Explorer, filters, single-fund views, comparison engine | Usable fund analytics |
| 4. Common intelligence foundation | Canonical entities, identifiers, aliases, sources, evidence provenance | Shared identity and evidence layer |
| 5. Portfolio intelligence | AMC disclosures, holdings, sector exposure, overlap | Stock-level fund exposure |
| 6. News and events | Exchange filings, event calendar, news discovery, watchlists | Verified news and event radar |
| 7. Social intelligence | Reddit and X connectors, entity resolution, sentiment, topics | Qualified public-discussion intelligence |
| 8. Document intelligence | PDF parsing, embeddings, Qdrant, retrieval and citations | Financial-document RAG |
| 9. Agent orchestration | LangGraph state, supervisor, specialist tools and synthesis | Evidence-grounded research workflow |
| 10. Frontend integration | Dashboard, comparison studio, charts, AI research interface | Complete user experience |
| 11. Evaluation and deployment | Financial tests, agent/RAG evaluation, Docker, monitoring | Tested deployable system |

## Evaluation and Reliability

The project should have separate evaluation suites.

### Financial correctness

- Validate calculations against independently computed examples.
- Test date boundaries, missing observations, holidays, and irregular cash flows.
- Test annualization and benchmark alignment.
- Test Growth and IDCW treatment separately.
- Check that comparison periods and frequencies are identical.

### Agent evaluation

- Correct agent routing.
- Correct tool selection and arguments.
- Structured-output validity.
- Error handling and retry behaviour.
- No unsupported numerical claims.

### Social intelligence evaluation

- Entity resolution accuracy.
- Sentiment classification quality.
- Sarcasm and context handling.
- Spam and duplicate detection.
- Coverage and source freshness.
- Separation of opinion, allegation, and verified fact.

### News and RAG evaluation

- Source credibility and freshness.
- Correct confirmed / unverified classification.
- Duplicate and outdated event detection.
- Retrieval relevance.
- Citation correctness.
- Faithfulness to retrieved documents.

Use LangSmith for tracing and experiments, alongside conventional Python unit tests and integration tests.

## Configuration

Create a local `.env` file and never commit API keys.

Example configuration (names only):

```dotenv
APP_ENV=development

DATABASE_URL=
QDRANT_URL=
QDRANT_API_KEY=

GROQ_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=

LANGSMITH_API_KEY=
LANGSMITH_TRACING=false
LANGSMITH_PROJECT=mutual-fund-agent-analysis

REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=

X_BEARER_TOKEN=

TAVILY_API_KEY=
```

Only configure providers that are actually used. Keep `.env` out of version control and provide a sanitized `.env.example`.

## Responsible Use and Data Limitations

- This is a personal research and educational project, not a guarantee of investment outcomes.
- Historical performance and social sentiment do not predict future returns.
- Clearly distinguish official disclosures, reputable reporting, opinions, rumours, and speculation.
- Link important claims to their original sources and timestamps.
- Never present unverified social posts as confirmed corporate information.
- Do not infer causation from sentiment and price correlations.
- Respect Reddit, X, news-provider, exchange, and data-vendor terms, access limits, attribution, and retention requirements.
- Do not train models on platform content unless the relevant rights and permissions explicitly allow it.
- Avoid storing deleted or restricted social content contrary to platform requirements.
- Show missing data, stale data, and calculation limitations rather than silently filling gaps.

---


## Local Development

### Requirements

- Python 3.11, 3.12, or 3.13.
- Docker Engine with Docker Compose.
- Git.

### Setup

```bash
git clone https://github.com/Souptik-Hazra/Mutual_Fund_Agent_Analysis.git
cd Mutual_Fund_Agent_Analysis

python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Create the local environment file and start PostgreSQL:

```bash
# Windows PowerShell
Copy-Item .env.example .env
# Linux / macOS
cp .env.example .env

docker compose up -d db
alembic upgrade head
```

Run the API locally:

```bash
uvicorn mutual_fund_agent_analysis.main:app --reload
```

Alternatively, start the complete Docker Compose stack with `docker compose up --build`. The one-shot `migrate` service applies Alembic migrations before the API starts.

- API documentation: http://localhost:8000/docs
- Liveness: http://localhost:8000/api/v1/health/live
- Readiness: http://localhost:8000/api/v1/health/ready

### Sync a scheme's NAV history

Find a scheme code using the [MFAPI scheme search endpoint](https://api.mfapi.in/mf/search?q=HDFC), then run:

```bash
mfa-sync-nav 125497 --start-date 2020-01-01
```

The command validates the provider response, upserts scheme metadata and source-specific NAV observations, and records the original provider payload in `provider_sync_runs`. NAV rows are keyed by scheme, date, and provider so different sources can be reconciled without overwriting one another. Re-running it is safe for the same scheme/date range. Use a real scheme code from the provider rather than assuming the example code is current.

### Import source-attributed scheme metadata and IDCW declarations
Register each source in the local `data_sources` table before importing. The migrations seed `amfi` and the generic `amc_disclosures` placeholder; for each AMC, prefer a distinct source key and its own official base URL:

```bash
mfa-register-source my_amc \
  --display-name "AMC legal name" \
  --source-type official \
  --authority-tier 1 \
  --base-url "https://official-amc-domain.example/" \
  --official --enabled
```

Replace the example name/domain with the actual source, after checking the AMC's official website and its applicable usage/attribution terms. Use `--disabled` until access and rights have been reviewed. A source's official flag is an operator assertion, not something the CLI independently certifies.


Register each source in the local `data_sources` table before importing. Record its true official status, base URL, terms URL and enabled state. The default import status is **unverified**; use `--verification-status verified` only after manually checking every row against the original official AMC/AMFI document. The CLI validates the source registry and URL host, but it cannot independently prove that a disclosure is complete or authentic.

Metadata CSV header:

```csv
scheme_code,source_url,valid_from,valid_to,plan_type,option_type,lifecycle_type,expense_ratio,expense_ratio_effective_date,benchmark_code,launch_date,closure_date,verification_note,metadata_json
```

IDCW CSV header:

```csv
scheme_code,source_url,external_id,revision,supersedes_distribution_id,ex_date,record_date,payment_date,amount_per_unit,option_type,status,published_at,metadata_json
```

Run the importers:

```bash
mfa-import-scheme-metadata data/scheme-metadata.csv --source-key amc-official
mfa-import-idcw data/idcw-distributions.csv --source-key amc-official
```

Use `--verification-status verified` only after manual source validation and only when the registered source is enabled, official, and has a matching `base_url`. For a correction, create a new distribution revision and set `supersedes_distribution_id` to the active prior record. Imports are idempotent; conflicting reuse of an existing revision is rejected.

**CSV import does not assert complete date coverage.** The IDCW total-return API remains blocked until a separate verified coverage attestation is created for the exact scheme, source and requested date interval. Review the imported rows and original notice before creating that attestation.

### Quality checks

```bash
ruff check .
ruff format --check .
pytest
```

The credentials in the local Docker Compose configuration are development-only. Replace them and use managed secrets before deploying anywhere beyond a personal development machine. Never commit `.env` or API keys.

## Initial Build Priority

Start by validating the data sources and scheme identifiers, then build NAV ingestion and a verified financial analytics engine. Implement single-fund analysis and daily/weekly/monthly/quarterly/yearly views, followed by multi-fund comparison. Add portfolio holdings and event/news ingestion next. Introduce LangGraph only after the core Python services and APIs work reliably; then add social intelligence and document RAG as separate subsystems. This keeps the first release useful even before every API or LLM integration is available.

The central design principle is:

**Reliable data + deterministic financial analytics + specialized AI agents + traceable research.**


## Multi-provider NAV ingestion and reconciliation

NAV ingestion supports two adapters behind one provider-neutral contract:

- \`mfapi\`: convenient scheme-specific historical JSON API.
- \`amfi\`: AMFI's public historical NAV report, fetched in windows of at most 7 days.

AMFI history is retrieved from \`https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx\`
using the \`tp=1\` open-ended-scheme report. The adapter parses the observed eight-column
historical layout and legacy six-column rows, filters the requested scheme, validates
dates and positive Decimal NAVs, and retains fetched source text in the provider audit
record. Zero-valued liquidation rows are excluded from price history. AMC/category
metadata is not inferred from report headings.

Examples:

\`\`\`bash
mfa-sync-nav 125497 --provider amfi --start-date 2024-01-01 --end-date 2024-12-31
mfa-sync-nav 125497 --provider mfapi --start-date 2024-01-01 --end-date 2024-12-31
\`\`\`

### Reconciliation policy (version 1)

- Preserve every provider observation independently using \`(scheme_code, nav_date, source)\`.
- Prefer AMFI as the canonical source; use MFAPI only when an AMFI observation is not yet present.
- Compare the maximum and minimum available provider NAVs for the same scheme/date.
- Classify a date as \`matched\` when the absolute spread is at most ₹0.0001, \`conflict\` when it is larger, and \`single_source\` when only one provider is available.
- Store all source values, canonical NAV/source, absolute and relative differences, tolerance, and evaluation timestamp in \`nav_reconciliations\`.
- Recompute reconciliation whenever a new observation for that date is ingested. Conflicts never overwrite or delete either provider's original NAV.

The ₹0.0001 threshold is an initial tolerance aligned to four-decimal NAV publication precision;
validate it against a larger sample before treating it as a permanent business rule. Canonical
source selection is a data convention, not a claim that independent published values are
economically identical.

AMFI adapter coverage currently targets open-ended scheme history (\`tp=1\`). Close-ended and
interval schemes, daily NAVAll bulk refresh, and scheme-master lifecycle tracking remain
separate follow-up work. Raw provider-response audit data has no automated purge job yet;
define deployment retention and backup policies before large-scale ingestion.


## Benchmark TRI ingestion

Benchmark ingestion stores the official Nifty Total Return Index (TRI) and Net Total Return
(NTR) series separately from mutual-fund NAVs. The Nifty Indices historical-data page publishes
a dedicated Total Returns Index Values report, with TRI and NTR columns. TRI includes
constituent dividends reinvested; compare a fund's Growth-option returns with TRI rather than
a price-only index. See the [Nifty Indices TRI explanation](https://www.niftyindices.com/resources/index-concepts/total-return-index)
and [historical-data reports](https://www.niftyindices.com/reports/historical-data).

The adapter currently calls the historical-data page's TRI endpoint. That endpoint is
reverse-engineered and is not a versioned public API, so it is isolated behind
\`NiftyIndicesClient\`, validates every row, and should be monitored for upstream schema or
access changes. Use canonical index names exactly as shown by Nifty Indices (for example,
\`NIFTY 50\`); an invalid/unavailable name returns no rows and is treated as an error.

Example:

\`\`\`bash
mfa-sync-benchmark "NIFTY 50" --start-date 2020-01-01 --end-date 2026-11-25
\`\`\`

The \`benchmark_indices\` table stores the benchmark master;
\`benchmark_observations\` stores daily TRI and optional NTR values keyed by benchmark,
date, and source; \`benchmark_sync_runs\` stores the original response and ingestion audit
metadata. Re-running a date range is idempotent. No TRI is synthesized from price-index
values or fund NAVs, and missing benchmark dates are not forward-filled.


## Deterministic financial analytics (Phase 2)

The analytics core accepts dated `Decimal` observations and performs deterministic calculations without network or LLM calls. The adjacent `analytics.service` module loads reconciled NAV and benchmark TRI observations from PostgreSQL and assembles a reproducible report. The public API exposes:

- Absolute point-to-point return and date-aware CAGR (365.25-day year).
- Consecutive-observation returns, 1Y/3Y/5Y rolling returns, trailing returns with explicit anchor-date staleness, and completed calendar-year returns.
- Annualized sample volatility, downside deviation, Sharpe, and Sortino ratios.
- Exact-date fund/benchmark return alignment, beta, arithmetic annualized Jensen alpha, and excess return.
- Maximum drawdown, peak/trough dates, recovery date, trough-to-recovery duration, and underwater duration.

Example:

```python
from datetime import date
from decimal import Decimal

from mutual_fund_agent_analysis.analytics import (
    PricePoint,
    absolute_return,
    cagr,
    calculate_drawdown,
    period_returns,
    calculate_risk_metrics,
)

navs = [
    PricePoint(date(2023, 1, 2), Decimal("100")),
    PricePoint(date(2023, 7, 3), Decimal("105")),
    PricePoint(date(2024, 1, 2), Decimal("112")),
]
print(absolute_return(navs))
print(cagr(navs))
sample_returns = period_returns(navs)
print(calculate_risk_metrics(sample_returns, periods_per_year=2))
print(calculate_drawdown(navs))
```

### Calculation conventions and limitations

- Inputs must be positive, finite prices with unique dates. They are sorted chronologically; duplicate dates are rejected.
- Returns are calculated between consecutive available observations. The package does not invent missing trading-day values or forward-fill NAV/benchmark series. If a source has missing sessions, the multi-session return is still treated as one observation; callers must validate coverage before applying a daily annualization factor.
- Rolling/trailing windows use calendar anniversaries (a leap-day anchor maps to February 28) and the closest observed value on or before the anchor date. `trailing_return_details` reports the target anchor, actual observation date, and staleness in days; callers may set `max_staleness_days` to reject stale anchors. CAGR uses 365.25 days per year.
- Volatility uses sample standard deviation. Annualization uses the caller-supplied frequency (252 daily periods by default; use 52 weekly, 12 monthly, 4 quarterly, 2 semiannual, or 1 yearly). Common frequencies are checked against median calendar spacing. The report includes median/max interval, long-gap count, and an estimated coverage ratio; these diagnostics do not fill missing observations.
- The risk-free rate is an explicitly supplied nominal annual rate divided by the observation frequency. It defaults to zero and must be disclosed by callers; the report retains the assumption used.
- Sharpe and Sortino are undefined when their respective denominators are zero or fewer than two return observations are available; these return `None`, not infinity.
- Beta and alpha use only exact common return intervals (both start and end dates). No date interpolation or forward-fill is performed. Benchmark output reports the fund/benchmark observation counts and aligned coverage ratio. Beta/alpha are undefined with fewer than two aligned observations or zero benchmark variance.
- Jensen alpha is arithmetic and annualized by multiplying the mean periodic CAPM intercept by the periods per year; it is not CAGR alpha. Reported annualized fund and benchmark returns are arithmetic mean returns multiplied by the periods per year, not geometric annualized returns.
- NAV price returns do not include cash distributions. Growth-option NAVs are the intended input for total-return comparisons; IDCW cash flows require a distribution-aware total-return series or cash-flow methodology.
- Calendar-year returns include a latest year ending on the final trading day only when that date is December 31 or the caller supplies an explicit `calendar_year_as_of_date` after December 31. The latest NAV must fall within the final seven calendar days of December when the explicit as-of date is used; this avoids marking stale mid-year data complete.
- The `analyze_fund(session, scheme_code, ...)` service reads canonical values from `nav_reconciliations` and benchmark TRI from `benchmark_observations`. It rejects unresolved NAV conflicts by default; callers must explicitly opt in to include canonical values from conflict dates. An HTTP endpoint is subsequent integration work.

Run the analytics tests with:

```bash
pytest tests/test_analytics.py
```


## Fund analysis API (Phase 3)

The Phase 3 backend exposes a scheme explorer and deterministic single-/multi-fund analysis. All analysis reads canonical reconciled NAVs; unresolved NAV conflicts are rejected unless the caller explicitly opts in. The API never fabricates missing NAV or TRI observations.

### Scheme discovery and explorer

- `GET /api/v1/schemes/discover?q=HDFC` searches MFAPI's scheme directory. This is an upstream lookup and does not write to PostgreSQL.
- `GET /api/v1/schemes?q=HDFC&fund_house=...&category=...&scheme_type=...&plan=direct&option=growth&limit=25&offset=0` filters the locally ingested scheme catalogue.
- `GET /api/v1/schemes/{scheme_code}` returns cached scheme metadata and the latest reconciled NAV/status.

The local explorer is intentionally backed by the database, so it only lists schemes already ingested through the NAV sync workflow. Use discovery to identify a scheme code, then ingest its NAV history before requesting analytics.

### Single-fund analysis

`GET /api/v1/schemes/{scheme_code}/analytics` accepts optional `start_date`, `end_date`, `benchmark_code`, `benchmark_source`, `annual_risk_free_rate`, `periods_per_year`, `allow_nav_conflicts`, and `calendar_year_as_of_date` query parameters. The response includes point-to-point return, CAGR, rolling and completed calendar-year returns, risk metrics, drawdown/recovery, benchmark attribution, and data-conflict provenance.

Example:

```http
GET /api/v1/schemes/125497/analytics?start_date=2020-01-01&benchmark_code=NIFTY%2050&periods_per_year=252
```

### Multi-fund comparison

`POST /api/v1/schemes/compare` accepts 2–5 unique scheme codes and a shared date range, optional benchmark, annual risk-free rate, annualization frequency, and NAV-conflict policy. Each fund is evaluated on the exact intersection of available NAV dates across all selected funds. When a benchmark is selected, TRI dates are also intersected. The response reports the common date range and observation count. No forward filling, interpolation, or raw-NAV-level comparison is performed.

Example request:

```json
{
  "scheme_codes": [125497, 120503],
  "start_date": "2021-01-01",
  "end_date": "2026-11-25",
  "benchmark_code": "NIFTY 50",
  "annual_risk_free_rate": "0",
  "periods_per_year": 252
}
```

### Phase 3 boundaries

This phase delivers backend API contracts and services, not a React dashboard. Expense ratios, AUM, fund-manager history, holdings, IDCW distribution-aware total returns, SIP/XIRR, and agent-generated narratives are not included because the current normalized database does not yet contain the required source data or workflows. Add those only with their own verified data models and methodology.


## Phase 4 — Common intelligence foundation

The shared identity and provenance layer is implemented on the development branch. It provides canonical entities, source-aware temporal aliases, namespaced identifiers, a source-authority registry, evidence records, entity-evidence links, and deterministic exact-match resolution. Ambiguous aliases are returned as candidates rather than silently resolved.

All endpoints are under `/api/v1/intelligence`:

- `GET /sources`: list registered sources and authority metadata.
- `POST /entities`, `GET /entities`, `GET /entities/{entity_id}`: create, search, list, and retrieve canonical entities with bounded pagination and type/status filters.
- `POST /entities/{entity_id}/aliases`, `GET /entities/{entity_id}/aliases`: register and list source-aware aliases and validity intervals.
- `POST /entities/{entity_id}/identifiers`, `GET /entities/{entity_id}/identifiers`: register and list unique namespaced identifiers.
- `POST /evidence`: record source references, publication/retrieval/effective dates, content hash, verification status, and confidence.
- `POST /entities/{entity_id}/evidence/{evidence_id}`: link evidence to an entity.
- `GET /entities/{entity_id}/evidence?limit=50&offset=0`: retrieve linked evidence with bounded pagination.
- `POST /entities/{entity_id}/relationships`, `GET /entities/{entity_id}/relationships`: manage typed, temporal links between entities.
- `POST /resolve`: resolve exact identifiers first and exact aliases second.

The migration seeds AMFI, MFAPI, Nifty Indices, SEBI, NSE, BSE, RBI, and MOSPI. Reddit and X are registered disabled by default; enabling them requires separate access, terms, and retention review. It also backfills canonical identities for existing schemes, AMCs, and benchmarks, including unverified scheme-to-AMC relationships. New NAV and benchmark ingestion maintains those identities and identifiers. NAV ingestion also registers AMC entities and an unverified `managed_by` relationship from the provider's fund-house field. NAV and benchmark sync runs now create hashed evidence references linked to their canonical entities while keeping full provider payloads in the existing audit tables. The original NAV/benchmark schemas and provider-sync audit records remain intact.

See [Phase 4 implementation notes](docs/phase-4-common-intelligence-foundation.md).


## Phases 9–11 — Personal research workspace

Phase 9 adds a LangGraph supervisor that routes questions to deterministic fund, portfolio, event, social and document research services, with optional LLM synthesis. Phase 10 adds the React/Vite workspace in `frontend/`. Phase 11 adds an offline routing benchmark and local operating guidance. Start with `docs/phases-9-11-personal.md` for setup and API usage. The optional LangGraph dependency is installed with `pip install -e ".[agents]"`; the Docker development image includes it automatically.


## Personal SIP and investor transaction workflows

The local **Investments** workspace separates simulated contributions from the actual personal
transaction ledger.

- `POST /api/v1/schemes/{scheme_code}/sip-simulation` runs a hypothetical monthly SIP using
  exact-date reconciled NAVs. Missing scheduled dates are reported as missed; no NAV is filled.
  The output identifies its return basis as `simulated_sip`.
- `POST /api/v1/schemes/{scheme_code}/transactions` appends a purchase, SIP, additional purchase,
  redemption, switch-in/out, dividend payout, charge, or tax entry.
- `GET /api/v1/schemes/{scheme_code}/transactions` lists the stored ledger with date filters
  and bounded pagination. `DELETE /api/v1/transactions/{transaction_id}` removes an incorrect
  manually entered entry.
- `GET /api/v1/schemes/{scheme_code}/investor-returns` calculates actual-ledger XIRR and
  realized/unrealized gain. Open units require an exact, reconciled, non-conflicted NAV.
  The response identifies its basis as `actual_ledger`.
- `GET /api/v1/schemes/{scheme_code}/active-risk` calculates tracking error and information ratio
  on exact fund/benchmark return intervals.

Transaction amounts and units are stored as positive magnitudes; the transaction type defines
the cash-flow sign. SIP simulation is never mixed into actual investor returns unless the user
also enters those transactions into the ledger. IDCW payouts entered manually are included as
cash inflows, but historical IDCW total-return series are not yet available until official
distribution disclosures, corrections, option mapping, and effective dates are ingested.

## Local backup and recovery

The local application data can be backed up and restored with the scripts in
`scripts/`. They protect the PostgreSQL database and configured Qdrant collection;
see [Local backup and recovery](docs/local-backup-recovery.md) for prerequisites,
checksums, retention, Qdrant version compatibility, and the destructive restore procedure.

```bash
./scripts/backup-local.sh
./scripts/restore-local.sh backups/mfa-backup-YYYYMMDDTHHMMSSZ.tar.gz
```

The restore command requires an explicit interactive confirmation. Backups are not encrypted
by these scripts; protect or encrypt the resulting archives before moving them off the machine.


## Financial reliability audit

After applying database migrations, generate a local coverage report:

```bash
mfa-audit-local --output artifacts/local-coverage-audit.json
```

For a bounded read-only MFAPI, AMFI and Nifty TRI provider check (maximum 31 calendar days), pass the exact scheme and benchmark identifiers:

```bash
mfa-audit-local --live --scheme-code YOUR_SCHEME_CODE --benchmark-code "NIFTY 50" \
  --start-date 2026-11-01 --end-date 2026-11-25
```

The added API contracts include `GET /api/v1/audit/coverage`, source-attributed scheme metadata observations, versioned IDCW records and coverage attestations, a guarded reinvested-IDCW index, and portfolio holding-quality diagnostics. Daily, weekly, monthly, quarterly and yearly analytics use actual observed period-end NAVs; missing values are never filled. Read the phase implementation notes before registering an official distribution source.
