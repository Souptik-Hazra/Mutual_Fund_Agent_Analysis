# Mutual Fund Agent Analysis

An AI-powered mutual fund research and market-intelligence platform focused initially on **Indian mutual funds**. The project combines quantitative fund analytics, multi-fund comparison, portfolio intelligence, financial-document research, social sentiment, and upcoming-news monitoring.

> **Project status:** Planning / initial setup. The capabilities described below are the intended product scope; they should not be interpreted as already implemented.

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

- Store raw source responses or source references where permitted.
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
| 1. Foundation | Repository setup, configuration, FastAPI, PostgreSQL, provider abstraction | Working application skeleton |
| 2. Data ingestion | Scheme master, historical NAV, validation, benchmark data | Reliable financial data layer |
| 3. Analytics engine | Returns, risk, rolling metrics, SIP calculations | Tested quantitative library |
| 4. Fund analysis | Explorer, filters, single-fund views, comparison engine | Usable fund analytics |
| 5. Agent orchestration | LangGraph state, supervisor, financial tools and agents | Working financial agent workflow |
| 6. Portfolio intelligence | AMC disclosures, holdings, sector exposure, overlap | Stock-level fund exposure |
| 7. Social intelligence | Reddit and X connectors, entity resolution, sentiment, topics | Stock and fund discussion analysis |
| 8. News and events | Exchange filings, event calendar, news discovery, watchlists | News and event radar |
| 9. Document intelligence | PDF parsing, embeddings, Qdrant, retrieval and citations | Financial-document RAG |
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

## Initial Build Priority

Start by validating the data sources and scheme identifiers, then build NAV ingestion and a verified financial analytics engine. Implement single-fund analysis and daily/weekly/monthly/quarterly/yearly views, followed by multi-fund comparison. Add portfolio holdings and event/news ingestion next. Introduce LangGraph only after the core Python services and APIs work reliably; then add social intelligence and document RAG as separate subsystems. This keeps the first release useful even before every API or LLM integration is available.

The central design principle is:

**Reliable data + deterministic financial analytics + specialized AI agents + traceable research.**
