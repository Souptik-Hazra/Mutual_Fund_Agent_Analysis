import { useEffect, useMemo, useState } from "react";
import { request } from "./api";
import { buildDocumentSearchPath, eventRows } from "./research";

const tabs = ["Overview", "Funds", "Compare", "Portfolio", "Investments", "Events", "Documents", "Assistant"];
const money = (value) => value == null ? "—" : Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const percent = (value) => value == null ? "—" : `${(Number(value) * 100).toFixed(2)}%`;

function Panel({ title, children, action }) { return <section className="panel"><div className="panel-head"><h2>{title}</h2>{action}</div>{children}</section>; }
function Empty({ children = "Run a query to see results." }) { return <p className="empty">{children}</p>; }

export default function App() {
  const [tab, setTab] = useState("Overview");
  const [health, setHealth] = useState("Checking API…");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);
  const [query, setQuery] = useState("");
  const [codes, setCodes] = useState("125497");
  const [benchmark, setBenchmark] = useState("NIFTY 50");
  const [analysisFrequency, setAnalysisFrequency] = useState("daily");
  const [question, setQuestion] = useState("Analyse performance, portfolio holdings and recent events");
  const [documentQuery, setDocumentQuery] = useState("expense ratio risk portfolio strategy");
  const [dateFrom, setDateFrom] = useState("2024-01-01");
  const [dateTo, setDateTo] = useState(new Date().toISOString().slice(0, 10));
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [documentTitle, setDocumentTitle] = useState("");
  const [sipAmount, setSipAmount] = useState("5000");
  const [sipDay, setSipDay] = useState("1");
  const [transactionDate, setTransactionDate] = useState(dateTo);
  const [transactionType, setTransactionType] = useState("purchase");
  const [transactionAmount, setTransactionAmount] = useState("5000");
  const [transactionUnits, setTransactionUnits] = useState("100");
  const [transactionNav, setTransactionNav] = useState("");
  const [transactionNotes, setTransactionNotes] = useState("");
  const schemeCodes = useMemo(() => codes.split(",").map((x) => Number(x.trim())).filter((x) => Number.isInteger(x) && x > 0), [codes]);

  useEffect(() => { fetch("/health/live").then((r) => r.ok ? r.json() : Promise.reject()).then(() => setHealth("API connected")).catch(() => setHealth("API offline")); }, []);
  async function run(fn) { setBusy(true); setError(""); setData(null); try { setData(await fn()); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  function json(method, body) { return { method, body: JSON.stringify(body) }; }
  const runFunds = () => run(() => request(query.trim() ? `/schemes?q=${encodeURIComponent(query.trim())}&limit=30` : "/schemes?limit=30"));
  const runFundAnalysis = (code) => { setCodes(String(code)); run(() => request(`/schemes/${code}/analytics?benchmark_code=${encodeURIComponent(benchmark)}&start_date=${dateFrom}&end_date=${dateTo}&frequency=${analysisFrequency}`)); };
  const runCompare = () => run(() => request("/schemes/compare", json("POST", { scheme_codes: schemeCodes, benchmark_code: benchmark || null, start_date: dateFrom, end_date: dateTo, frequency: analysisFrequency })));
  const runPortfolio = () => run(async () => {
    const snapshot = await request(`/portfolios/${schemeCodes[0]}`);
    const quality = await request(`/portfolios/${schemeCodes[0]}/quality`);
    return { ...snapshot, quality };
  });
  const runEvents = () => run(() => request(`/events/fund-exposure/${schemeCodes[0]}?start_date=${dateFrom}&end_date=${dateTo}`));
  const runDocuments = () => run(() => request(buildDocumentSearchPath(documentQuery, schemeCodes[0])));
  const runAssistant = () => run(() => request("/assistant/research", json("POST", { question, scheme_codes: schemeCodes, benchmark_code: benchmark || null, start_date: dateFrom, end_date: dateTo })));
  const runSipSimulation = () => {
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    return run(() => request(`/schemes/${schemeCodes[0]}/sip-simulation`, json("POST", {
      start_date: dateFrom, end_date: dateTo, valuation_date: dateTo,
      monthly_amount: sipAmount, day_of_month: Number(sipDay),
    })));
  };
  const loadTransactions = () => {
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    return run(() => request(`/schemes/${schemeCodes[0]}/transactions`));
  };
  const loadInvestorReturns = () => {
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    return run(() => request(`/schemes/${schemeCodes[0]}/investor-returns`));
  };
  const addTransaction = () => {
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    const unitTypes = ["purchase", "sip", "additional_purchase", "redemption", "switch_in", "switch_out"];
    const payload = {
      transaction_date: transactionDate, transaction_type: transactionType,
      amount: transactionAmount,
      units: unitTypes.includes(transactionType) ? transactionUnits : null,
      nav: transactionNav ? transactionNav : null,
      notes: transactionNotes.trim() || null,
    };
    return run(async () => {
      const result = await request(`/schemes/${schemeCodes[0]}/transactions`, json("POST", payload));
      setTransactionNotes("");
      return result;
    });
  };
  async function importDocument() {
    if (!selectedDocument) return setError("Choose a PDF first.");
    const form = new FormData();
    form.append("file", selectedDocument);
    form.append("source_key", "amc_disclosures");
    form.append("title", documentTitle || selectedDocument.name);
    if (schemeCodes[0]) form.append("scheme_code", String(schemeCodes[0]));
    await run(() => request("/documents/upload", { method: "POST", body: form }));
  }
  async function importPortfolio() {
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    if (!selectedFile) return setError("Choose a normalized AMC CSV or XLSX file first.");
    const form = new FormData();
    form.append("file", selectedFile);
    form.append("scheme_code", String(schemeCodes[0]));
    form.append("effective_date", dateTo);
    await run(() => request("/portfolios/import-file", { method: "POST", body: form }));
  }

  return <div className="shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">MF</span><div><strong>Fund Intelligence</strong><small>Personal research workspace</small></div></div><nav>{tabs.map((item) => <button key={item} className={tab === item ? "nav-item active" : "nav-item"} onClick={() => { setTab(item); setData(null); setError(""); }}>{item}</button>)}</nav><div className="sidebar-foot"><span className={health === "API connected" ? "dot online" : "dot"}></span>{health}<small>Local API · localhost:8000</small></div></aside>
    <main className="main"><header className="topbar"><div><p className="eyebrow">INDIA · MUTUAL FUND RESEARCH</p><h1>{tab}</h1></div><div className="top-actions"><span className="status-pill">{health}</span><span className="date-label">{new Date().toLocaleDateString("en-IN", { dateStyle: "medium" })}</span></div></header>
      <div className="workspace">
        {tab === "Overview" && <><div className="hero"><div><p className="eyebrow">RESEARCH CONSOLE</p><h2>Understand funds beyond returns.</h2><p>Analyse performance, portfolio exposure, disclosures, events and evidence in one workspace.</p><button className="primary" onClick={() => setTab("Assistant")}>Start research <span>→</span></button></div><div className="hero-art"><div className="orb orb-one"></div><div className="orb orb-two"></div><div className="hero-stat"><small>RESEARCH ENGINE</small><strong>5 specialist agents</strong><span>LangGraph orchestration</span></div></div></div><div className="stat-grid"><div className="stat-card"><span>01</span><strong>Fund analytics</strong><small>CAGR · risk · drawdown · TRI</small></div><div className="stat-card"><span>02</span><strong>Portfolio intelligence</strong><small>Holdings · sectors · overlap</small></div><div className="stat-card"><span>03</span><strong>Evidence research</strong><small>Events · social · documents</small></div></div><Panel title="Quick start"><p className="muted">Enter scheme codes once, then use the same selection across the research modules.</p><div className="field"><label>Scheme codes (comma-separated)</label><input value={codes} onChange={(e) => setCodes(e.target.value)} /></div><div className="field-row"><div className="field"><label>From</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div><div className="field"><label>To</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div></div></Panel></>}
        {tab === "Funds" && <Panel title="Scheme explorer"><div className="toolbar"><input placeholder="Search fund name or scheme code" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && runFunds()} /><select value={analysisFrequency} onChange={(e) => setAnalysisFrequency(e.target.value)}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option></select><button className="primary" disabled={busy} onClick={runFunds}>Search</button></div>{data?.items?.length ? <div className="table-wrap"><table><thead><tr><th>Scheme</th><th>Scheme code</th><th>Fund house</th><th>Category</th><th>Action</th></tr></thead><tbody>{data.items.map((x) => <tr key={x.scheme_code}><td>{x.scheme_name}</td><td>{x.scheme_code}</td><td>{x.fund_house || "—"}</td><td>{x.scheme_category || "—"}</td><td><button className="text-button" onClick={() => runFundAnalysis(x.scheme_code)}>Analyse</button></td></tr>)}</tbody></table></div> : <Empty>{data?.scheme_code ? "Analytics loaded below." : data ? "No matching locally ingested schemes." : "Search your local scheme catalogue."}</Empty>}</Panel>}{data?.scheme_code && <Panel title={`Fund analytics · ${data.scheme_code}`}><div className="analysis-grid"><div className="metric"><small>CAGR</small><strong>{percent(data.cagr)}</strong></div><div className="metric"><small>Absolute return</small><strong>{percent(data.absolute_return)}</strong></div><div className="metric"><small>Annual volatility</small><strong>{percent(data.risk?.annualized_volatility)}</strong></div><div className="metric"><small>Max drawdown</small><strong>{percent(data.drawdown?.max_drawdown)}</strong></div></div><p className="muted">Sampling frequency: {data.frequency || "daily"} · {data.observation_count} observations · {data.start_date} to {data.end_date}</p></Panel>}
        {tab === "Compare" && <><Panel title="Fund comparison"><div className="field"><label>Scheme codes</label><input value={codes} onChange={(e) => setCodes(e.target.value)} /></div><div className="field-row"><div className="field"><label>Benchmark TRI</label><input value={benchmark} onChange={(e) => setBenchmark(e.target.value)} /></div><div className="field"><label>Start date</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div><div className="field"><label>End date</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div><div className="field"><label>Return frequency</label><select value={analysisFrequency} onChange={(e) => setAnalysisFrequency(e.target.value)}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option></select></div></div><button className="primary" disabled={busy || schemeCodes.length < 2} onClick={runCompare}>Compare funds</button></Panel>{data?.funds && <Panel title="Comparison results"><div className="table-wrap"><table><thead><tr><th>Scheme</th><th>Absolute return</th><th>CAGR</th><th>Volatility</th><th>Max drawdown</th></tr></thead><tbody>{data.funds.map((f) => <tr key={f.scheme_code}><td>{f.scheme_code}</td><td>{percent(f.absolute_return)}</td><td>{percent(f.cagr)}</td><td>{percent(f.risk?.annualized_volatility)}</td><td>{percent(f.drawdown?.max_drawdown)}</td></tr>)}</tbody></table></div><p className="muted">{data.observation_count} common observations · {data.frequency || analysisFrequency} sampling · {data.start_date} to {data.end_date}</p></Panel>}</>}
        {tab === "Portfolio" && <><Panel title="Portfolio snapshot"><div className="toolbar"><input value={codes} onChange={(e) => setCodes(e.target.value)} /><button className="primary" disabled={busy} onClick={runPortfolio}>Load holdings</button></div><div className="toolbar upload"><input type="file" accept=".csv,.xlsx" onChange={(e) => setSelectedFile(e.target.files?.[0] || null)} /><button className="secondary" disabled={busy} onClick={importPortfolio}>Import disclosure</button></div></Panel>{data?.holdings && <Panel title={`Holdings · effective ${data.effective_date}`}><div className="table-wrap"><table><thead><tr><th>Security</th><th>Asset class</th><th>Sector</th><th>Weight</th></tr></thead><tbody>{data.holdings.slice(0, 30).map((h, i) => <tr key={i}><td>{h.security_name}</td><td>{h.asset_class}</td><td>{h.sector || "—"}</td><td>{h.weight_pct == null ? "—" : `${h.weight_pct}%`}</td></tr>)}</tbody></table></div><p className="muted">Weight coverage: {money(data.weight_coverage_pct)}% · HHI: {money(data.hhi_0_to_1)}</p>{data.quality && <p className="muted">Unresolved equity exposure: {money(data.quality.unresolved_equity_weight_pct)}% · Resolved equity coverage: {money(data.quality.resolved_equity_coverage_pct)}%</p>}<div className="allocation-list">{data.sector_allocation?.slice(0, 10).map((sector) => <div className="allocation-row" key={sector.sector}><span>{sector.sector}</span><div className="allocation-track"><i style={{ width: `${Math.max(0, Math.min(100, Number(sector.weight_pct)))}%` }} /></div><b>{money(sector.weight_pct)}%</b></div>)}</div></Panel>}</>}

        {tab === "Investments" && <>
          <Panel title="Investment inputs">
            <p className="muted">These workflows are stored locally in your PostgreSQL database. Simulated SIPs are hypothetical; ledger XIRR uses only transactions you enter.</p>
            <div className="field"><label>Scheme code</label><input value={codes} onChange={(e) => setCodes(e.target.value)} /></div>
            <div className="field-row">
              <div className="field"><label>Start date</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
              <div className="field"><label>End / valuation date</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
            </div>
          </Panel>
          <Panel title="Historical SIP simulation">
            <div className="field-row">
              <div className="field"><label>Monthly amount (₹)</label><input type="number" min="0.01" step="0.01" value={sipAmount} onChange={(e) => setSipAmount(e.target.value)} /></div>
              <div className="field"><label>Installment day (1–31)</label><input type="number" min="1" max="31" value={sipDay} onChange={(e) => setSipDay(e.target.value)} /></div>
            </div>
            <button className="primary" disabled={busy || !schemeCodes[0]} onClick={runSipSimulation}>Simulate SIP</button>
            {data?.return_basis === "simulated_sip" && <>
              <div className="analysis-grid">
                <div className="metric"><small>Invested</small><strong>₹{money(data.invested_amount)}</strong></div>
                <div className="metric"><small>Current value</small><strong>₹{money(data.current_value)}</strong></div>
                <div className="metric"><small>Absolute gain</small><strong>₹{money(data.absolute_gain)}</strong></div>
                <div className="metric"><small>Simulated XIRR</small><strong>{percent(data.xirr)}</strong></div>
              </div>
              <p className="muted">{data.invested_count}/{data.scheduled_count} instalments invested · {data.missed_count} missed exact-date NAVs · {percent(data.coverage_ratio)} schedule coverage</p>
              <div className="table-wrap"><table><thead><tr><th>Due date</th><th>Amount</th><th>NAV</th><th>Units</th><th>Status</th></tr></thead><tbody>{data.installments.map((item) => <tr key={item.due_date}><td>{item.due_date}</td><td>₹{money(item.amount)}</td><td>{item.nav ?? "—"}</td><td>{money(item.units)}</td><td>{item.status}</td></tr>)}</tbody></table></div>
            </>}
          </Panel>
          <Panel title="Actual investor transaction ledger">
            <div className="field-row">
              <div className="field"><label>Transaction date</label><input type="date" value={transactionDate} onChange={(e) => setTransactionDate(e.target.value)} /></div>
              <div className="field"><label>Transaction type</label><select value={transactionType} onChange={(e) => setTransactionType(e.target.value)}>
                <option value="purchase">Purchase</option><option value="sip">SIP</option><option value="additional_purchase">Additional purchase</option><option value="redemption">Redemption</option><option value="switch_in">Switch in</option><option value="switch_out">Switch out</option><option value="dividend_payout">Dividend payout</option><option value="charges">Charges</option><option value="tax">Tax</option>
              </select></div>
            </div>
            <div className="field-row">
              <div className="field"><label>Amount (₹)</label><input type="number" min="0.01" step="0.01" value={transactionAmount} onChange={(e) => setTransactionAmount(e.target.value)} /></div>
              {["purchase", "sip", "additional_purchase", "redemption", "switch_in", "switch_out"].includes(transactionType) && <div className="field"><label>Units</label><input type="number" min="0.00000001" step="0.00000001" value={transactionUnits} onChange={(e) => setTransactionUnits(e.target.value)} /></div>}
              {["purchase", "sip", "additional_purchase", "redemption", "switch_in", "switch_out"].includes(transactionType) && <div className="field"><label>Optional NAV</label><input type="number" min="0.00000001" step="0.00000001" value={transactionNav} onChange={(e) => setTransactionNav(e.target.value)} /></div>}
            </div>
            <div className="field"><label>Notes</label><input value={transactionNotes} onChange={(e) => setTransactionNotes(e.target.value)} placeholder="Optional transaction note" /></div>
            <div className="toolbar">
              <button className="primary" disabled={busy || !schemeCodes[0]} onClick={addTransaction}>Save transaction</button>
              <button className="secondary" disabled={busy || !schemeCodes[0]} onClick={loadTransactions}>Refresh ledger</button>
              <button className="secondary" disabled={busy || !schemeCodes[0]} onClick={loadInvestorReturns}>Calculate investor returns</button>
            </div>
            {Array.isArray(data) && <div className="table-wrap"><table><thead><tr><th>Date</th><th>Type</th><th>Amount</th><th>Units</th><th>NAV</th></tr></thead><tbody>{data.map((item) => <tr key={item.transaction_id}><td>{item.transaction_date}</td><td>{item.transaction_type}</td><td>₹{money(item.amount)}</td><td>{item.units == null ? "—" : money(item.units)}</td><td>{item.nav ?? "—"}</td></tr>)}</tbody></table>{!data.length && <Empty>No transactions have been entered for this scheme.</Empty>}</div>}
            {data?.return_basis === "actual_ledger" && <>
              <div className="analysis-grid">
                <div className="metric"><small>Cash invested</small><strong>₹{money(data.cash_invested)}</strong></div>
                <div className="metric"><small>Realized proceeds</small><strong>₹{money(data.realized_proceeds)}</strong></div>
                <div className="metric"><small>Current value</small><strong>₹{money(data.current_value)}</strong></div>
                <div className="metric"><small>Absolute gain</small><strong>₹{money(data.absolute_gain)}</strong></div>
              </div>
              <p className="muted">Actual investor XIRR: {percent(data.xirr)} · {data.total_units} remaining units · {data.transaction_count} ledger entries</p>
              {data.xirr_limitation && <p className="muted">XIRR limitation: {data.xirr_limitation}</p>}
            </>}
            {data?.transaction_id && <p className="muted">Transaction #{data.transaction_id} saved. Refresh the ledger to view all entries.</p>}
          </Panel>
        </>}
        {tab === "Events" && <Panel title="Events mapped to fund exposure"><div className="field-row"><div className="field"><label>Scheme code</label><input value={codes} onChange={(e) => setCodes(e.target.value)} /></div><div className="field"><label>From</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div><div className="field"><label>To</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div></div><button className="primary" disabled={busy} onClick={runEvents}>Load events</button>{eventRows(data).length ? <div className="event-list">{eventRows(data).map((event) => <article className="event-row" key={event.event_id}><div><strong>{event.title}</strong><small>{event.event_date || "Date unavailable"} · {event.status} · {event.source_key || "source unknown"}</small></div><b>{event.exposure_found ? `${money(event.aggregate_exposure_pct)}% exposure` : "No mapped exposure"}</b></article>)}</div> : <Empty>{data ? "No linked events found for this period." : "Load event-to-holdings mapping."}</Empty>}</Panel>}
        {tab === "Documents" && <Panel title="Document research"><div className="upload-block"><div className="field"><label>Upload a text-based PDF factsheet, SID or disclosure</label><input type="file" accept="application/pdf,.pdf" onChange={(e) => setSelectedDocument(e.target.files?.[0] || null)} /></div><div className="field"><label>Document title</label><input value={documentTitle} onChange={(e) => setDocumentTitle(e.target.value)} placeholder="Optional title (defaults to filename)" /></div><button className="secondary" disabled={busy} onClick={importDocument}>Upload and index PDF</button></div><div className="toolbar"><input value={documentQuery} onChange={(e) => setDocumentQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && runDocuments()} /><button className="primary" disabled={busy} onClick={runDocuments}>Search documents</button></div>{data?.document_id ? <div className="upload-success"><strong>PDF uploaded successfully</strong><p>{data.title} · Document #{data.document_id} · {data.page_count} page(s)</p><small>Document stored. Search the indexed documents above to retrieve relevant excerpts.</small></div> : data?.results?.length ? data.results.map((item, i) => <article className="document-result" key={i}><div><strong>{item.title}</strong><small>Page {item.page_number || "—"} · {item.retrieval_mode || data.retrieval_mode}</small></div><p>{item.text}</p><small>Document #{item.document_id} · chunk #{item.citation?.chunk_id || item.chunk_index}</small></article>) : <Empty>{data ? "No matching document chunks." : "Search indexed PDFs and factsheets."}</Empty>}</Panel>}
        {tab === "Assistant" && <><Panel title="Research assistant"><p className="muted">Ask a question. LangGraph routes it to the relevant research specialists; deterministic services calculate financial metrics.</p><div className="field"><label>Question</label><textarea rows="4" value={question} onChange={(e) => setQuestion(e.target.value)} /></div><div className="field"><label>Scheme codes (optional, comma-separated)</label><input value={codes} onChange={(e) => setCodes(e.target.value)} /></div><div className="field-row"><div className="field"><label>Benchmark TRI (optional)</label><input value={benchmark} onChange={(e) => setBenchmark(e.target.value)} /></div><div className="field"><label>Start date</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div><div className="field"><label>End date</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div></div><button className="primary" disabled={busy} onClick={runAssistant}>{busy ? "Researching…" : "Run research"}</button></Panel>{data && <><Panel title="Research synthesis"><p className="answer">{data.answer}</p><div className="chip-row">{data.intents?.map((intent) => <span className="chip" key={intent}>{intent}</span>)}</div>{data.model_used && <small className="muted">Synthesized with {data.model_used}</small>}</Panel><Panel title="Evidence and citations">{data.citations?.length ? data.citations.map((c, i) => <div className="citation" key={i}><strong>{c.type}</strong><small>{JSON.stringify(c)}</small></div>) : <Empty>No source references were returned.</Empty>}</Panel><Panel title="Structured evidence"><details><summary>Show retrieved tool outputs</summary><pre className="json-evidence">{JSON.stringify(data.results, null, 2)}</pre></details></Panel>{data.errors?.length > 0 && <Panel title="Data limitations"><ul>{data.errors.map((e) => <li key={e}>{e}</li>)}</ul></Panel>}</>}</>}
        {busy && <div className="loading"><span></span> Working…</div>}{error && <div className="error">{error}</div>}
      </div><footer>Personal workspace · Metrics are deterministic · AI summaries are evidence-bounded</footer></main>
  </div>;
}
