import { useEffect, useMemo, useState } from "react";
import { request, streamRequest } from "./api";
import { buildDocumentSearchPath, eventRows, isBenchmarkObservationUnavailable } from "./research";
import AdvancedIntelligence from "./AdvancedIntelligence";

const tabs = ["Overview", "Funds", "Compare", "Portfolio", "Investments", "Category & Equity", "Events", "Social", "Documents", "Fund Profile", "Actual Exposure", "Security Intelligence", "Assistant"];
const money = (value) => value == null ? "—" : Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const percent = (value) => value == null ? "—" : `${(Number(value) * 100).toFixed(2)}%`;
const localDateString = (value = new Date()) => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};
function PerformanceChart({ series = [] }) {
  const [activeIndex, setActiveIndex] = useState(null);
  const points = series.map((point) => ({
    date: Array.isArray(point) ? point[0] : point.date,
    value: Number(Array.isArray(point) ? point[1] : point.value),
  })).filter((point) => Number.isFinite(point.value));
  if (points.length < 2) return null;
  const width = 1000, height = 300, padX = 18, padY = 24;
  const values = points.map((point) => point.value);
  const min = Math.min(...values), max = Math.max(...values);
  const spread = max - min || 1;
  const coords = points.map((point, index) => ({
    ...point,
    x: padX + index / (points.length - 1) * (width - padX * 2),
    y: height - padY - (point.value - min) / spread * (height - padY * 2),
  }));
  const selected = activeIndex == null ? null : coords[activeIndex];
  const handlePointer = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width * width;
    const index = Math.max(0, Math.min(coords.length - 1, Math.round((x - padX) / (width - padX * 2) * (coords.length - 1))));
    setActiveIndex(index);
  };
  return <div className="performance-chart">
    <div className="chart-legend"><span><i className="legend-up" /> Gain</span><span><i className="legend-down" /> Decline</span><span className="muted">Hover or tap the chart to inspect NAV index</span></div>
    <svg className="performance-svg" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Interactive fund performance chart. Green segments show increases and red segments show declines." onPointerMove={handlePointer} onPointerLeave={() => setActiveIndex(null)} onClick={handlePointer}>
      {[0, .25, .5, .75, 1].map((fraction) => <line key={fraction} x1={padX} x2={width - padX} y1={padY + fraction * (height - padY * 2)} y2={padY + fraction * (height - padY * 2)} className="chart-gridline" />)}
      {coords.slice(1).map((point, index) => <line key={index} x1={coords[index].x} y1={coords[index].y} x2={point.x} y2={point.y} className={point.value >= coords[index].value ? "chart-segment gain" : "chart-segment loss"} />)}
      {selected && <><line x1={selected.x} x2={selected.x} y1={padY} y2={height - padY} className="chart-crosshair" /><circle cx={selected.x} cy={selected.y} r="6" className="chart-active-point" /></>}
      <rect x="0" y="0" width={width} height={height} fill="transparent" />
    </svg>
    <div className="chart-readout" aria-live="polite">{selected ? <><strong>{selected.value.toFixed(3)}</strong><span>{selected.date || `Observation ${activeIndex + 1}`}</span><small>{activeIndex > 0 ? `${selected.value >= coords[activeIndex - 1].value ? "+" : ""}${(selected.value - coords[activeIndex - 1].value).toFixed(3)} vs previous observation` : "First observation"}</small></> : <span>Move over the graph to inspect a data point</span>}</div>
    <div className="chart-axis"><span>{points[0].date || "Start"}</span><span>{points[points.length - 1].date || "Latest"}</span></div>
    <small className="muted">Indexed fund return series, starting at 100; green indicates an increase from the previous observation and red indicates a decrease.</small>
  </div>;
}

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
  const [compareSearch, setCompareSearch] = useState("");
  const [compareResults, setCompareResults] = useState([]);
  const [compareSelected, setCompareSelected] = useState([]);
  const [benchmark, setBenchmark] = useState("");
  const [benchmarkResolution, setBenchmarkResolution] = useState(null);
  const [categoryBenchmark, setCategoryBenchmark] = useState("");
  const [analysisFrequency, setAnalysisFrequency] = useState("daily");
  const [question, setQuestion] = useState("Analyse performance, portfolio holdings and recent events");
  const [synthesize, setSynthesize] = useState(false);
  const [documentQuery, setDocumentQuery] = useState("expense ratio risk portfolio strategy");
  const [dateFrom, setDateFrom] = useState("2024-01-01");
  const [dateTo, setDateTo] = useState(localDateString());
  const [selectedFile, setSelectedFile] = useState(null);
  const [selectedDocument, setSelectedDocument] = useState(null);
  const [documentTitle, setDocumentTitle] = useState("");
  const [eventStatus, setEventStatus] = useState("");
  const [eventSearch, setEventSearch] = useState("");
  const [eventResults, setEventResults] = useState([]);
  const [eventScheme, setEventScheme] = useState(null);
  const [assistantSearch, setAssistantSearch] = useState("");
  const [assistantResults, setAssistantResults] = useState([]);
  const [assistantSelected, setAssistantSelected] = useState([]);
  const [eventSource, setEventSource] = useState("");
  const [eventSources, setEventSources] = useState([]);
  const [eventFeedUrl, setEventFeedUrl] = useState("");
  const [eventData, setEventData] = useState(null);
  const [eventCollection, setEventCollection] = useState(null);
  const [socialSource, setSocialSource] = useState("");
  const [socialProviders, setSocialProviders] = useState(null);
  const [socialImportSource, setSocialImportSource] = useState("reddit");
  const [selectedSocialFile, setSelectedSocialFile] = useState(null);
  const [streamProgress, setStreamProgress] = useState([]);
  const [sipAmount, setSipAmount] = useState("5000");
  const [sipDay, setSipDay] = useState("1");
  const [transactionDate, setTransactionDate] = useState(dateTo);
  const [transactionType, setTransactionType] = useState("purchase");
  const [transactionAmount, setTransactionAmount] = useState("5000");
  const [transactionUnits, setTransactionUnits] = useState("100");
  const [transactionNav, setTransactionNav] = useState("");
  const [transactionNotes, setTransactionNotes] = useState("");
  const schemeCodes = useMemo(() => codes.split(",").map((x) => Number(x.trim())).filter((x) => Number.isInteger(x) && x > 0), [codes]);

  async function resolveBenchmarkForCodes(targetCodes, asOf, override = "") {
    if (override.trim()) {
      const result = { availability: "overridden", benchmark: { code: override.trim(), source: "niftyindices", source_key: null }, mappings: [] };
      setBenchmarkResolution(result);
      return result;
    }
    if (!targetCodes.length) {
      const result = { availability: "unavailable", benchmark: null, mappings: [] };
      setBenchmarkResolution(result);
      return result;
    }
    const mappings = await Promise.all(targetCodes.map(async (code) => {
      const params = asOf ? "?as_of=" + encodeURIComponent(asOf) : "";
      return await request("/fund-intelligence/schemes/" + code + "/benchmark" + params);
    }));
    const first = mappings[0]?.benchmark;
    const common = Boolean(first) && mappings.every((item) =>
      item.availability === "mapped" && item.benchmark?.code === first.code && item.benchmark?.source === first.source && item.benchmark?.source_key === first.source_key
    );
    const result = {
      availability: common ? "mapped" : mappings.some((item) => item.availability === "mapped") ? "not_common" : "unmapped",
      benchmark: common ? first : null,
      mappings,
    };
    setBenchmarkResolution(result);
    return result;
  }
  const benchmarkDescription = benchmarkResolution?.benchmark
    ? "Benchmark " + benchmarkResolution.benchmark.code + " · source " + (benchmarkResolution.benchmark.source_name || benchmarkResolution.benchmark.source) +
      " · effective " + (benchmarkResolution.benchmark.effective_from || "unknown") + " to " +
      (benchmarkResolution.benchmark.effective_to || "open-ended")
    : benchmarkResolution?.availability === "overridden"
      ? "User override: " + benchmarkResolution.benchmark.code + " · source " + benchmarkResolution.benchmark.source
      : benchmarkResolution?.availability === "not_common"
        ? "Selected schemes do not share one effective benchmark mapping; benchmark metrics will be omitted."
        : "No valid official effective-dated mapping; fund-only analysis will be used unless you enter an explicit override.";

  useEffect(() => { request("/health/live").then(() => setHealth("API connected")).catch(() => setHealth("API offline")); }, []);
  useEffect(() => {
    if (tab === "Social") request("/social/providers").then((result) => setSocialProviders(result.providers || {})).catch(() => setSocialProviders({}));
  }, [tab]);
  async function run(fn) { setBusy(true); setError(""); setData(null); try { setData(await fn()); } catch (e) { setError(e.message); } finally { setBusy(false); } }
  function json(method, body) { return { method, body: JSON.stringify(body) }; }
  const runFunds = () => run(() => request(query.trim() ? `/schemes?q=${encodeURIComponent(query.trim())}&limit=30` : "/schemes?limit=30"));
  const runFundAnalysis = (code) => {
    setCodes(String(code));
    return run(async () => {
      await request("/schemes/" + code + "/sync-nav", { method: "POST" });
      const selection = await resolveBenchmarkForCodes([code], dateTo, benchmark);
      const params = new URLSearchParams({ start_date: dateFrom, end_date: dateTo, frequency: analysisFrequency });
      if (selection.benchmark) {
        params.set("benchmark_code", selection.benchmark.code);
        params.set("benchmark_source", selection.benchmark.source);
      }
      try {
        const report = await request("/schemes/" + code + "/analytics?" + params.toString());
        return { ...report, benchmark_selection: selection };
      } catch (error) {
        if (selection.availability !== "mapped" || !isBenchmarkObservationUnavailable(error)) throw error;
        params.delete("benchmark_code");
        params.delete("benchmark_source");
        const report = await request("/schemes/" + code + "/analytics?" + params.toString());
        return {
          ...report,
          benchmark_selection: { ...selection, availability: "mapped_data_unavailable", benchmark: null },
          benchmark_unavailable_reason: "The effective mapping exists, but its TRI observations were unavailable: " + error.message,
        };
      }
    });
  };
  const searchCompareSchemes = async () => {
    const term = compareSearch.trim();
    if (term.length < 2) {
      setError("Enter at least 2 characters to search for a scheme.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const result = await request("/schemes?q=" + encodeURIComponent(term) + "&limit=30");
      setCompareResults(result.items || []);
      if (!result.items?.length) setError("No matching schemes found. Try a different name.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const addCompareScheme = (scheme) => {
    if (compareSelected.some((item) => item.scheme_code === scheme.scheme_code)) return;
    if (compareSelected.length >= 5) {
      setError("You can compare a maximum of 5 schemes.");
      return;
    }
    const next = [...compareSelected, scheme];
    setCompareSelected(next);
    setCodes(next.map((item) => item.scheme_code).join(","));
  };
  const removeCompareScheme = (schemeCode) => {
    const next = compareSelected.filter((item) => item.scheme_code !== schemeCode);
    setCompareSelected(next);
    setCodes(next.map((item) => item.scheme_code).join(","));
  };
  const runCompare = () => {
    if (schemeCodes.length < 2 || schemeCodes.length > 5) {
      setError("Enter 2 to 5 valid scheme codes, separated by commas, to compare funds.");
      return;
    }
    return run(async () => {
    await Promise.all(schemeCodes.map((code) =>
      request("/schemes/" + code + "/sync-nav", { method: "POST" })
    ));
    const selection = await resolveBenchmarkForCodes(schemeCodes, dateTo, benchmark);
    const payload = {
      scheme_codes: schemeCodes,
      benchmark_code: selection.benchmark?.code || null,
      benchmark_source: selection.benchmark?.source || "niftyindices",
      start_date: dateFrom, end_date: dateTo, frequency: analysisFrequency,
    };
    try {
      const result = await request("/schemes/compare", json("POST", payload));
      return { ...result, benchmark_selection: selection };
    } catch (error) {
      if (selection.availability !== "mapped" || !isBenchmarkObservationUnavailable(error)) throw error;
      payload.benchmark_code = null;
      const result = await request("/schemes/compare", json("POST", payload));
      return {
        ...result,
        benchmark_selection: { ...selection, availability: "mapped_data_unavailable", benchmark: null },
        comparability_warnings: [
          ...(result.comparability_warnings || []),
          "The effective benchmark mapping exists, but TRI observations were unavailable: " + error.message,
        ],
      };
    }
    });
  };
  const runCategoryAnalysis = () => {
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    return run(async () => {
      const selection = await resolveBenchmarkForCodes([schemeCodes[0]], dateTo, categoryBenchmark);
      const params = new URLSearchParams({ start_date: dateFrom, end_date: dateTo });
      if (selection.benchmark) {
        params.set("benchmark_code", selection.benchmark.code);
        params.set("benchmark_source", selection.benchmark.source);
      }
      try {
        const result = await request("/fund-intelligence/schemes/" + schemeCodes[0] + "/category?" + params.toString());
        return { ...result, benchmark_selection: selection };
      } catch (error) {
        if (selection.availability !== "mapped" || !isBenchmarkObservationUnavailable(error)) throw error;
        params.delete("benchmark_code");
        params.delete("benchmark_source");
        const result = await request("/fund-intelligence/schemes/" + schemeCodes[0] + "/category?" + params.toString());
        return {
          ...result,
          benchmark_selection: { ...selection, availability: "mapped_data_unavailable", benchmark: null },
          benchmark_unavailable_reason: "The effective mapping exists, but TRI observations were unavailable: " + error.message,
        };
      }
    });
  };
  const runEquityStatus = () => {
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    return run(() => request(`/fund-intelligence/schemes/${schemeCodes[0]}/equity-status?as_of=${encodeURIComponent(dateTo)}`));
  };
  const runEquityComparison = () => {
    if (schemeCodes.length < 2 || schemeCodes.length > 5) return setError("Enter two to five scheme codes.");
    return run(() => request("/fund-intelligence/compare", json("POST", { scheme_codes: schemeCodes })));
  };
  const runPortfolio = () => run(async () => {
    const asOf = encodeURIComponent(dateTo);
    const snapshot = await request(`/portfolios/${schemeCodes[0]}?as_of=${asOf}`);
    const quality = await request(`/portfolios/${schemeCodes[0]}/quality?as_of=${asOf}`);
    return { ...snapshot, quality };
  });
  const searchEventSchemes = async () => {
    const term = eventSearch.trim();
    if (term.length < 2) return setError("Enter at least 2 characters to search for a scheme.");
    setBusy(true);
    setError("");
    try {
      const result = await request("/schemes?q=" + encodeURIComponent(term) + "&limit=30");
      setEventResults(result.items || []);
      if (!result.items?.length) setError("No matching schemes found. Try another name.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const runEvents = async () => {
    const selectedCode = eventScheme?.scheme_code || schemeCodes[0];
    if (!selectedCode) return setError("Search and select a fund before loading events.");
    const params = new URLSearchParams({ start_date: dateFrom, end_date: dateTo, limit: "100" });
    params.set("as_of", new Date(`${dateTo}T23:59:59+05:30`).toISOString());
    if (eventStatus) params.set("status", eventStatus);
    if (eventSource.trim()) params.set("source_key", eventSource.trim());
    setBusy(true); setError(""); setEventData(null);
    try {
      const [listing, exposure] = await Promise.all([
        request(`/events?${params.toString()}`),
        request(`/events/fund-exposure/${selectedCode}?start_date=${dateFrom}&end_date=${dateTo}`),
      ]);
      const exposureById = new Map((exposure.events || []).map((item) => [item.event_id, item]));
      setEventData({
        ...listing,
        events: (listing.items || []).map((item) => ({ ...item, ...(exposureById.get(item.event_id) || {}) })),
        exposure_summary: exposure,
      });
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const collectEventFeed = async () => {
    const source = eventSources.find((item) => item.source_key === eventSource);
    if (!source) return setError("Select an official source before collecting.");
    if (!source.ready) return setError("This source is not approved for collection. Complete its terms and access review first.");
    if (!eventFeedUrl.trim()) return setError("Enter the verified RSS/Atom feed URL.");
    setBusy(true); setError(""); setEventCollection(null);
    try {
      const result = await request(`/events/collect/${encodeURIComponent(source.source_key)}?feed_url=${encodeURIComponent(eventFeedUrl.trim())}`, { method: "POST" });
      setEventCollection(result);
      const refreshed = await request("/events/sources");
      setEventSources(refreshed.items || []);
      await runEvents();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const runSocial = () => run(async () => {
    const params = new URLSearchParams({ start_date: dateFrom, end_date: dateTo });
    if (socialSource) params.set("source_key", socialSource);
    const analytics = await request(`/social/analytics?${params.toString()}`);
    let fund = null;
    if (schemeCodes[0]) {
      try {
        fund = await request(`/social/funds/${schemeCodes[0]}/sentiment?start_date=${dateFrom}&end_date=${dateTo}`);
      } catch (error) {
        fund = { unavailable_reason: error.message };
      }
    }
    return { analytics, fund };
  });
  const runDocuments = () => run(() => request(buildDocumentSearchPath(documentQuery, schemeCodes[0])));
  const searchAssistantSchemes = async () => {
    const term = assistantSearch.trim();
    if (term.length < 2) return setError("Enter at least 2 characters to search for a scheme.");
    setBusy(true);
    setError("");
    try {
      const result = await request("/schemes?q=" + encodeURIComponent(term) + "&limit=30");
      setAssistantResults(result.items || []);
      if (!result.items?.length) setError("No matching schemes found. Try another name.");
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };
  const addAssistantScheme = (scheme) => {
    if (assistantSelected.some((item) => item.scheme_code === scheme.scheme_code)) return;
    if (assistantSelected.length >= 5) return setError("Select a maximum of 5 schemes.");
    const next = [...assistantSelected, scheme];
    setAssistantSelected(next);
    setCodes(next.map((item) => item.scheme_code).join(","));
  };
  const removeAssistantScheme = (schemeCode) => {
    const next = assistantSelected.filter((item) => item.scheme_code !== schemeCode);
    setAssistantSelected(next);
    setCodes(next.map((item) => item.scheme_code).join(","));
  };
  async function runAssistant() {
    setBusy(true);
    setError("");
    setData(null);
    setStreamProgress([]);
    try {
      if (schemeCodes.length) {
        await Promise.all(
          schemeCodes.map((code) =>
            request("/schemes/" + code + "/sync-nav", { method: "POST" })
          )
        );
      }
      const selection = await resolveBenchmarkForCodes(schemeCodes, dateTo, benchmark);
      const result = await streamRequest(
        "/assistant/research/stream",
        { question, scheme_codes: schemeCodes, benchmark_code: selection.benchmark?.code || null, benchmark_source: selection.benchmark?.source || null, start_date: dateFrom, end_date: dateTo, as_of_date: dateTo, synthesize },
        (progress) => setStreamProgress((current) => [...current, progress]),
      );
      setData(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
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
  async function importSocialDataset() {
    if (!socialImportSource) return setError("Choose the source represented by this export.");
    if (!selectedSocialFile) return setError("Choose a CSV or JSON social export first.");
    const form = new FormData();
    form.append("source", socialImportSource);
    form.append("file", selectedSocialFile);
    await run(() => request("/social/import-file", { method: "POST", body: form }));
  }

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
        {tab === "Overview" && <><div className="hero"><div><p className="eyebrow">RESEARCH CONSOLE</p><h2>Understand funds beyond returns.</h2><p>Analyse performance, portfolio exposure, disclosures, events and evidence in one workspace.</p><button className="primary" onClick={() => setTab("Assistant")}>Start research <span>→</span></button></div><div className="hero-art"><div className="orb orb-one"></div><div className="orb orb-two"></div><div className="hero-stat"><small>RESEARCH ENGINE</small><strong>8 research specialists</strong><span>LangGraph orchestration</span></div></div></div><div className="stat-grid"><div className="stat-card"><span>01</span><strong>Fund analytics</strong><small>CAGR · risk · drawdown · TRI</small></div><div className="stat-card"><span>02</span><strong>Portfolio intelligence</strong><small>Holdings · sectors · overlap</small></div><div className="stat-card"><span>03</span><strong>Category & investor analysis</strong><small>Peer rankings · actual ledger exposure</small></div><div className="stat-card"><span>04</span><strong>Security intelligence</strong><small>Underlying shares · quotes · dated fundamentals</small></div></div><Panel title="Quick start"><p className="muted">Enter scheme codes once, then use the same selection across the research modules.</p><div className="field"><label>Scheme codes (comma-separated)</label><input value={codes} onChange={(e) => setCodes(e.target.value)} /></div><div className="field-row"><div className="field"><label>From</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div><div className="field"><label>To</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div></div></Panel></>}
        {tab === "Funds" && <Panel title="Scheme explorer"><div className="toolbar"><input placeholder="Search fund name or scheme code" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && runFunds()} /><select value={analysisFrequency} onChange={(e) => setAnalysisFrequency(e.target.value)}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option></select><button className="primary" disabled={busy} onClick={runFunds}>Search</button></div>{data?.items?.length ? <div className="table-wrap"><table><thead><tr><th>Scheme</th><th>Scheme code</th><th>Fund house</th><th>Category</th><th>Action</th></tr></thead><tbody>{data.items.map((x) => <tr key={x.scheme_code}><td>{x.scheme_name}</td><td>{x.scheme_code}</td><td>{x.fund_house || "—"}</td><td>{x.scheme_category || "—"}</td><td><button className="text-button" onClick={() => runFundAnalysis(x.scheme_code)}>Analyse</button></td></tr>)}</tbody></table></div> : <Empty>{data?.scheme_code ? "Analytics loaded below." : data ? "No matching locally ingested schemes." : "Search your local scheme catalogue."}</Empty>}</Panel>}{data?.scheme_code && <Panel title={`Fund analytics · ${data.scheme_code}`}><div className="analysis-grid"><div className="metric"><small>CAGR (geometric)</small><strong>{percent(data.cagr)}</strong></div><div className="metric"><small>Absolute return</small><strong>{percent(data.absolute_return)}</strong></div><div className="metric"><small>Annual volatility</small><strong>{percent(data.risk?.annualized_volatility)}</strong></div><div className="metric"><small>Max drawdown</small><strong>{percent(data.drawdown?.maximum_drawdown)}</strong></div></div><p className="muted">Return basis: {data.return_basis || "unknown"} · Distribution coverage: {data.distribution_coverage_status || "not reported"} · Sampling: {data.frequency || "daily"} · {data.observation_count} observations · {data.start_date} to {data.end_date}</p>{data.benchmark_unavailable_reason && <p className="muted">{data.benchmark_unavailable_reason}</p>}{data.benchmark_selection && <p className="muted">{benchmarkDescription}</p>}{data.base100_series?.length > 1 && <PerformanceChart series={data.base100_series} />}<details><summary>Calculation methodology</summary><ul>{Object.entries(data.methodology || {}).map(([key, value]) => <li key={key}><strong>{key.replaceAll("_", " ")}:</strong> {value}</li>)}</ul></details>{data.risk?.coverage && <p className="muted">Observation coverage: {data.risk.coverage.inferred_frequency} · {data.risk.coverage.long_gap_count} long gap(s) · maximum interval {data.risk.coverage.maximum_interval_days ?? "—"} day(s) · estimated coverage {percent(data.risk.coverage.estimated_coverage_ratio)}</p>}</Panel>}
        {tab === "Compare" && <><Panel title="Fund comparison"><div className="field"><label>Search and select funds by name</label><div className="toolbar"><input value={compareSearch} onChange={(e) => setCompareSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchCompareSchemes()} placeholder="Search scheme name, e.g. Axis Corporate Bond" /><button className="secondary" disabled={busy || compareSearch.trim().length < 2} onClick={searchCompareSchemes}>Search</button></div><small className="muted">Select 2–5 schemes. Search results come from your locally imported catalogue.</small></div>{compareSelected.length > 0 && <div className="field"><label>Selected funds ({compareSelected.length}/5)</label><div className="event-list">{compareSelected.map((scheme) => <article className="event-row" key={scheme.scheme_code}><div><strong>{scheme.scheme_name}</strong><small>{scheme.fund_house || "Fund house unavailable"} · {scheme.scheme_category || "Category unavailable"} · Code {scheme.scheme_code}</small></div><button className="secondary" onClick={() => removeCompareScheme(scheme.scheme_code)}>Remove</button></article>)}</div></div>}{compareResults.length > 0 && <div className="field"><label>Search results</label><div className="table-wrap"><table><thead><tr><th>Scheme</th><th>Fund house</th><th>Category</th><th>Action</th></tr></thead><tbody>{compareResults.map((scheme) => <tr key={scheme.scheme_code}><td>{scheme.scheme_name}<small>Code {scheme.scheme_code}</small></td><td>{scheme.fund_house || "—"}</td><td>{scheme.scheme_category || "—"}</td><td><button className="secondary" disabled={compareSelected.some((item) => item.scheme_code === scheme.scheme_code) || compareSelected.length >= 5} onClick={() => addCompareScheme(scheme)}>{compareSelected.some((item) => item.scheme_code === scheme.scheme_code) ? "Added" : "Add"}</button></td></tr>)}</tbody></table></div></div>}<div className="field-row"><div className="field"><label>Benchmark TRI override (optional)</label><input value={benchmark} onChange={(e) => setBenchmark(e.target.value)} placeholder="Leave blank to use a common verified mapping" /></div><div className="field"><label>Start date</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div><div className="field"><label>End date</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div><div className="field"><label>Return frequency</label><select value={analysisFrequency} onChange={(e) => setAnalysisFrequency(e.target.value)}><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="quarterly">Quarterly</option><option value="yearly">Yearly</option></select></div></div><p className="muted">{benchmarkDescription}</p><button className="primary" disabled={busy || compareSelected.length < 2} onClick={runCompare}>Compare funds</button></Panel>{data?.funds && <Panel title="Comparison results"><div className="table-wrap"><table><thead><tr><th>Scheme</th><th>Return basis</th><th>Absolute return</th><th>CAGR</th><th>Volatility</th><th>Max drawdown</th></tr></thead><tbody>{data.funds.map((f) => <tr key={f.scheme_code}><td>{f.scheme_code}</td><td>{f.return_basis || "unknown"}</td><td>{percent(f.absolute_return)}</td><td>{percent(f.cagr)}</td><td>{percent(f.risk?.annualized_volatility)}</td><td>{percent(f.drawdown?.maximum_drawdown)}</td></tr>)}</tbody></table></div><p className="muted">{data.observation_count} common observations · {data.frequency || analysisFrequency} sampling · {data.start_date} to {data.end_date}</p>{data.benchmark_selection && <p className="muted">{benchmarkDescription}</p>}{data.comparability_warnings?.map((warning, index) => <p className="muted" key={index}>{warning}</p>)}</Panel>}</>}
        {tab === "Portfolio" && <><Panel title="Portfolio snapshot"><div className="toolbar"><input value={codes} onChange={(e) => setCodes(e.target.value)} /><button className="primary" disabled={busy} onClick={runPortfolio}>Load holdings</button></div><div className="toolbar upload"><input type="file" accept=".csv,.xlsx" onChange={(e) => setSelectedFile(e.target.files?.[0] || null)} /><button className="secondary" disabled={busy} onClick={importPortfolio}>Import disclosure</button></div></Panel>{data?.holdings && <Panel title={`Holdings · effective ${data.effective_date}`}><div className="table-wrap"><table><thead><tr><th>Security</th><th>Asset class</th><th>Sector</th><th>Weight</th></tr></thead><tbody>{data.holdings.slice(0, 30).map((h, i) => <tr key={i}><td>{h.security_name}</td><td>{h.asset_class}</td><td>{h.sector || "—"}</td><td>{h.weight_pct == null ? "—" : `${h.weight_pct}%`}</td></tr>)}</tbody></table></div><p className="muted">Weight coverage: {money(data.weight_coverage_pct)}% · HHI: {money(data.hhi_0_to_1)}</p>{data.quality && <><p className="muted">Unresolved equity exposure: {money(data.quality.unresolved_equity_weight_pct)}% · Resolved equity coverage: {money(data.quality.resolved_equity_coverage_pct)}%</p>{data.quality.quality_warnings?.map((warning, index) => <p className="muted" key={index}>Data quality: {warning}</p>)}</>}<div className="allocation-list">{data.sector_allocation?.slice(0, 10).map((sector) => <div className="allocation-row" key={sector.sector}><span>{sector.sector}</span><div className="allocation-track"><i style={{ width: `${Math.max(0, Math.min(100, Number(sector.weight_pct)))}%` }} /></div><b>{money(sector.weight_pct)}%</b></div>)}</div></Panel>}</>}

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
        {tab === "Category & Equity" && <>
          <Panel title="Category-relative fund analysis">
            <p className="muted">Compare the selected scheme with funds sharing its stored category, scheme type, plan and option. Use a category-appropriate benchmark TRI where available.</p>
            <div className="field-row">
              <div className="field"><label>Scheme codes</label><input value={codes} onChange={(e) => setCodes(e.target.value)} /></div>
              <div className="field"><label>Benchmark TRI override (optional)</label><input value={categoryBenchmark} onChange={(e) => setCategoryBenchmark(e.target.value)} placeholder="Leave blank to resolve the effective official mapping" /></div>
            </div>
            <div className="field-row">
              <div className="field"><label>From</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
              <div className="field"><label>To</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
            </div>
            <p className="muted">{benchmarkDescription}</p>
            <div className="toolbar">
              <button className="primary" disabled={busy} onClick={runCategoryAnalysis}>Analyse category peers</button>
              <button className="secondary" disabled={busy} onClick={runEquityStatus}>Check underlying equities</button>
              <button className="secondary" disabled={busy || schemeCodes.length < 2 || schemeCodes.length > 5} onClick={runEquityComparison}>Compare holdings (2–5 funds)</button>
            </div>
          </Panel>
          {data?.selected_fund && <Panel title={`Category peers · ${data.category}`}>
            <div className="analysis-grid">
              <div className="metric"><small>Peer count</small><strong>{data.peer_count}</strong></div>
              <div className="metric"><small>CAGR rank</small><strong>{data.selected_fund.cagr_rank ?? "—"} / {data.peer_count}</strong></div>
              <div className="metric"><small>CAGR percentile</small><strong>{data.selected_fund.cagr_percentile == null ? "—" : `${money(data.selected_fund.cagr_percentile)}%`}</strong></div>
              <div className="metric"><small>Sharpe rank</small><strong>{data.selected_fund.sharpe_ratio_rank ?? "—"} / {data.peer_count}</strong></div>
            </div>
            <p className="muted">Cohort: {data.peer_definition?.scheme_type || "—"} · {data.peer_definition?.plan_type || "—"} · {data.peer_definition?.option_type || "—"} · benchmark {data.benchmark_code || "not selected"}</p>{data.comparison_window && <p className="muted">Common observation window: {data.comparison_window.start_date} to {data.comparison_window.end_date} · {data.comparison_window.observation_count} observations</p>}{data.benchmark_selection && <p className="muted">{benchmarkDescription}</p>}
            <div className="table-wrap peer-table-wrap"><table className="peer-table"><thead><tr><th>Scheme</th><th>CAGR</th><th>Volatility</th><th>Sharpe</th><th>Max drawdown</th><th>Benchmark TRI (ann.)</th><th>Alpha (ann.)</th><th>Beta</th><th>TRI coverage</th><th>Rank</th></tr></thead><tbody>{data.peers?.map((peer) => <tr key={peer.scheme_code}><td className="peer-scheme-cell"><strong>{peer.scheme_name}</strong><small>Code {peer.scheme_code}</small><small>{peer.fund_house || "Fund house unavailable"}</small></td><td>{percent(peer.cagr)}</td><td>{percent(peer.annualized_volatility)}</td><td>{money(peer.sharpe_ratio)}</td><td>{percent(peer.maximum_drawdown)}</td><td>{percent(peer.benchmark?.annualized_benchmark_return)}</td><td>{percent(peer.benchmark?.annualized_alpha)}</td><td>{money(peer.benchmark?.beta)}</td><td>{percent(peer.benchmark?.coverage_ratio)}</td><td>{peer.cagr_rank ?? "—"}</td></tr>)}</tbody></table></div>
            <p className="muted">Return basis: {data.selected_fund.return_basis || "unknown"} · IDCW distribution coverage: {data.selected_fund.distribution_coverage_status || "not reported"}. Benchmark metrics use aligned TRI intervals and are suppressed when return bases are not comparable. {data.excluded_peer_count} peer(s) excluded for insufficient history or incompatible observations. {data.cohort_truncated ? `Ranking is limited to the first ${data.peer_limit} matching peers and is not a complete category-wide rank. ` : ""}Rankings are descriptive, not recommendations.</p>
          </Panel>}
          {data?.items && <Panel title={`Underlying equity status · holdings as of ${data.holdings_as_of}`}>
            <p className="muted">Disclosure status: {data.snapshot_status || "unknown"} · This is the latest available AMC disclosure, not a live fund portfolio.</p>
            <div className="analysis-grid">
              <div className="metric"><small>Equity securities</small><strong>{data.equity_security_count}</strong></div>
              <div className="metric"><small>Market observations</small><strong>{data.market_data_available_count}</strong></div>
            </div>
            <div className="table-wrap"><table><thead><tr><th>Security</th><th>Fund weight</th><th>Last price</th><th>Day change</th><th>Market status</th><th>Freshness</th></tr></thead><tbody>{data.items.map((item) => <tr key={item.security_key}><td>{item.security_name}<small>{item.isin || item.security_key}</small></td><td>{item.disclosed_weight_pct == null ? "—" : `${money(item.disclosed_weight_pct)}%`}</td><td>{item.market_data ? money(item.market_data.last_price) : "Unavailable"}</td><td>{item.market_data?.change_pct == null ? "—" : `${money(item.market_data.change_pct)}%`}</td><td>{item.market_data?.market_status || "—"}</td><td>{item.freshness || "—"}</td></tr>)}</tbody></table></div>
            {data.items.filter((item) => item.market_data?.health_signals?.length).map((item) => <p className="muted" key={item.security_key}><strong>{item.security_name}:</strong> {item.market_data.health_signals.map((signal) => signal.message).join(" ")}</p>)}
            {data.items.filter((item) => item.market_data).map((item) => <details key={item.security_key}><summary>{item.security_name} · source, fundamentals and corporate events</summary><p className="muted">Source: {item.market_data.source_key || "unknown"} · Observed: {item.market_data.observed_at || "unknown"} · Retrieved: {item.market_data.retrieved_at || "unknown"} · Fundamentals effective: {item.market_data.fundamentals_as_of || "unknown"} · Freshness: {item.freshness || "unknown"}</p>{item.market_data.source_url && <a href={item.market_data.source_url} target="_blank" rel="noreferrer">Open provider source</a>}<h4>Available fundamentals</h4><pre className="json-evidence">{JSON.stringify(item.market_data.fundamentals || {}, null, 2)}</pre><h4>Corporate events</h4><pre className="json-evidence">{JSON.stringify(item.market_data.corporate_events || [], null, 2)}</pre></details>)}
            <p className="muted">{data.warning} Market status is based on the latest stored provider observation, not a live exchange connection.</p>
          </Panel>}
          {data?.pairwise_overlap && <Panel title="Multi-fund equity overlap">
            <div className="table-wrap"><table><thead><tr><th>Fund A</th><th>Fund B</th><th>Overlap</th><th>Common shares</th></tr></thead><tbody>{data.pairwise_overlap.map((pair) => <tr key={`${pair.scheme_a}-${pair.scheme_b}`}><td>{pair.scheme_a}</td><td>{pair.scheme_b}</td><td>{money(pair.overlap_pct)}% {pair.overlap_is_lower_bound ? "(lower bound)" : ""}</td><td>{pair.common_security_count}</td></tr>)}</tbody></table></div>
            <h3>Equal-weighted combined exposure</h3>
            <div className="table-wrap"><table><thead><tr><th>Underlying share</th><th>Funds present</th><th>Combined exposure</th></tr></thead><tbody>{data.aggregated_equity_exposure?.slice(0, 30).map((item) => <tr key={item.security_key}><td>{item.name}<small>{item.security_key}</small></td><td>{item.funds_present}</td><td>{money(item.equal_weight_exposure_pct)}%</td></tr>)}</tbody></table></div>
            {data.has_partial_disclosures && <p className="muted">Warning: at least one fund has a partial holdings disclosure. Overlap and combined exposure may be understated.</p>}
            <p className="muted">{data.aggregation_basis} {data.disclosure_warning}</p>
          </Panel>}
        </>}
        {tab === "Events" && <Panel title="Event and news intelligence"><div className="field"><label>Search fund by name</label><div className="toolbar"><input value={eventSearch} onChange={(e) => setEventSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchEventSchemes()} placeholder="Search scheme name, e.g. Axis Corporate Bond" /><button className="secondary" disabled={busy || eventSearch.trim().length < 2} onClick={searchEventSchemes}>Search</button></div></div>{eventScheme && <div className="event-row"><div><strong>{eventScheme.scheme_name}</strong><small>{eventScheme.fund_house || "Fund house unavailable"} · {eventScheme.scheme_category || "Category unavailable"} · Code {eventScheme.scheme_code}</small></div><button className="secondary" onClick={() => setEventScheme(null)}>Change fund</button></div>}{eventResults.length > 0 && <div className="table-wrap"><table><thead><tr><th>Scheme</th><th>Fund house</th><th>Category</th><th>Action</th></tr></thead><tbody>{eventResults.map((scheme) => <tr key={scheme.scheme_code}><td>{scheme.scheme_name}<small>Code {scheme.scheme_code}</small></td><td>{scheme.fund_house || "—"}</td><td>{scheme.scheme_category || "—"}</td><td><button className="secondary" onClick={() => { setEventScheme(scheme); setEventResults([]); }}>Select</button></td></tr>)}</tbody></table></div>}<div className="field-row"><div className="field"><label>From</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div><div className="field"><label>To</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div></div><div className="field-row"><div className="field"><label>Status</label><select value={eventStatus} onChange={(e) => setEventStatus(e.target.value)}><option value="">All statuses</option>{["confirmed","scheduled","reported","unverified","speculative","disproved","outdated"].map((value) => <option key={value}>{value}</option>)}</select></div><div className="field"><label>Source key (optional)</label><input value={eventSource} onChange={(e) => setEventSource(e.target.value)} placeholder="e.g. nse_announcements" /></div></div><Panel title="Official source ingestion">
          <p className="muted">Only collect from an official RSS/Atom feed after independently verifying its URL, access rights and terms. Collection does not certify event claims.</p>
          <div className="field-row">
            <div className="field"><label>Official source</label><select value={eventSource} onChange={(e) => { setEventSource(e.target.value); const source = eventSources.find((item) => item.source_key === e.target.value); setEventFeedUrl(source?.feed_url || ""); }}><option value="">Select source</option>{eventSources.map((source) => <option key={source.source_key} value={source.source_key}>{source.display_name || source.source_key}</option>)}</select></div>
            <div className="field"><label>Verified RSS/Atom feed URL</label><input value={eventFeedUrl} onChange={(e) => setEventFeedUrl(e.target.value)} placeholder="https://official-domain.example/feed.xml" /></div>
          </div>
          {eventSource && (() => { const source = eventSources.find((item) => item.source_key === eventSource); return source ? <p className="muted">{source.ready ? "Ready for collection" : "Not approved for collection"} · {source.readiness_reason || "All source checks passed."} · Registered host: {source.base_url || "missing"}</p> : null; })()}
          <button className="secondary" disabled={busy || !eventSource} onClick={collectEventFeed}>Collect official events</button>
          {eventCollection && <p className="muted">Fetched {eventCollection.fetched} · new {eventCollection.created} · refreshed {eventCollection.updated}</p>}
          <div className="analysis-grid">{eventSources.map((source) => <div className="metric" key={source.source_key}><small>{source.display_name || source.source_key}</small><strong>{source.ready ? "Ready" : "Review required"}</strong><small>{source.enabled ? "Enabled" : "Disabled"} · {source.terms_url ? "Terms URL set" : "Terms URL missing"}</small></div>)}</div>
        </Panel>
        <Panel title="Event and fund exposure results">
          <div className="field-row"><div className="field"><label>From</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div><div className="field"><label>To</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div></div>
          <div className="field"><label>Status</label><select value={eventStatus} onChange={(e) => setEventStatus(e.target.value)}><option value="">All statuses</option>{["confirmed","scheduled","reported","unverified","speculative","disproved","outdated"].map((value) => <option key={value}>{value}</option>)}</select></div>
          <button className="primary" disabled={busy} onClick={runEvents}>Load events and fund exposure</button>
          {eventData?.events?.length ? <><p className="muted">{eventData.count} events · {eventData.exposure_summary?.count || 0} exposure records · fund {eventData.exposure_summary?.scheme_code}</p><div className="event-list">{eventData.events.map((event) => <article className="event-row" key={event.event_id}><div><strong>{event.title}</strong><small>{event.event_date || "Effective date unavailable"} · published {event.published_at || "unknown"} · {event.status} · {event.source_key || "source unknown"}</small><small>Evidence: {event.evidence?.verification_status || "not linked"} · authority tier {event.source?.authority_tier ?? "—"}</small>{event.canonical_url && <a href={event.canonical_url} target="_blank" rel="noreferrer">Open source</a>}</div><b>{event.exposure_found ? `${money(event.aggregate_exposure_pct)}% exposure` : event.reason || "No matching historical holding"}</b></article>)}</div></> : <Empty>{eventData ? "No events were collected for this filter and date range. Check source readiness above, then collect from an approved feed." : "Load collected events or collect from a verified official feed above."}</Empty>}
        </Panel></Panel>}
        {tab === "Documents" && <Panel title="Document research"><div className="upload-block"><div className="field"><label>Upload a text-based PDF factsheet, SID or disclosure</label><input type="file" accept="application/pdf,.pdf" onChange={(e) => setSelectedDocument(e.target.files?.[0] || null)} /></div><div className="field"><label>Document title</label><input value={documentTitle} onChange={(e) => setDocumentTitle(e.target.value)} placeholder="Optional title (defaults to filename)" /></div><button className="secondary" disabled={busy} onClick={importDocument}>Upload and index PDF</button></div><div className="toolbar"><input value={documentQuery} onChange={(e) => setDocumentQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && runDocuments()} /><button className="primary" disabled={busy} onClick={runDocuments}>Search documents</button></div>{data?.document_id ? <div className="upload-success"><strong>PDF uploaded successfully</strong><p>{data.title} · Document #{data.document_id} · {data.page_count} page(s)</p><small>Document stored. Search the indexed documents above to retrieve relevant excerpts.</small></div> : data?.results?.length ? data.results.map((item, i) => <article className="document-result" key={i}><div><strong>{item.title}</strong><small>Page {item.page_number || "—"} · {item.retrieval_mode || data.retrieval_mode}</small></div><p>{item.text}</p><small>Document #{item.document_id} · chunk #{item.citation?.chunk_id || item.chunk_index}</small></article>) : <Empty>{data ? "No matching document chunks." : "Search indexed PDFs and factsheets."}</Empty>}</Panel>}
        {tab === "Social" && <><Panel title="Social intelligence"><p className="muted">Provider discussion volume and independently evaluated sentiment only. Social signals are not verified facts or return predictors.</p></Panel><Panel title="Provider availability">{socialProviders ? <div className="analysis-grid">{Object.entries(socialProviders).map(([provider, info]) => <div className="metric" key={provider}><small>{provider === "x" ? "X" : "Reddit"}</small><strong>{info.status === "ready" ? "Ready" : info.status === "not_configured" ? "Not configured" : info.status === "disabled" ? "Disabled" : "Review required"}</strong><small>{info.can_collect ? "Official API collection available" : info.can_import ? "Reviewed manual import available" : "No collection/import until source approval"}</small></div>)}</div> : <Empty>Checking provider configuration…</Empty>}<p className="muted">Credentials are optional. Missing API keys do not affect fund, portfolio, news or document analysis.</p></Panel><Panel title="Import an authorized social export"><p className="muted">Import up to 500 records from a CSV or JSON export. The selected source must be enabled and have reviewed terms/access metadata. Raw post text is not retained.</p><div className="field-row"><div className="field"><label>Source</label><select value={socialImportSource} onChange={(e) => setSocialImportSource(e.target.value)}><option value="reddit">Reddit</option><option value="x">X</option></select></div><div className="field"><label>CSV or JSON file</label><input type="file" accept=".csv,.json,application/json,text/csv" onChange={(e) => setSelectedSocialFile(e.target.files?.[0] || null)} /></div></div><button className="secondary" disabled={busy || !selectedSocialFile} onClick={importSocialDataset}>Import social dataset</button>{data?.imported != null && <p className="muted">Imported {data.imported} records · sentiment: {data.sentiment_status}</p>}</Panel><Panel title="Social analytics"><p className="muted">Provider discussion volume and independently evaluated sentiment only. Social signals are not verified facts or return predictors.</p><div className="field-row"><div className="field"><label>Scheme code</label><input value={codes} onChange={(e) => setCodes(e.target.value)} /></div><div className="field"><label>From</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div><div className="field"><label>To</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div><div className="field"><label>Provider</label><select value={socialSource} onChange={(e) => setSocialSource(e.target.value)}><option value="">All providers</option><option value="reddit">Reddit</option><option value="x">X</option></select></div></div><button className="primary" disabled={busy} onClick={runSocial}>Load social analytics</button></Panel>{data?.analytics && <><Panel title="Discussion coverage"><div className="analysis-grid"><div className="metric"><small>Total posts</small><strong>{money(data.analytics.post_count ?? data.analytics.total_posts ?? 0)}</strong></div><div className="metric"><small>Scored posts</small><strong>{money(data.analytics.scored_post_count ?? 0)}</strong></div><div className="metric"><small>Unscored posts</small><strong>{money(data.analytics.unscored_post_count ?? 0)}</strong></div><div className="metric"><small>Average sentiment</small><strong>{data.analytics.average_sentiment == null ? "—" : money(data.analytics.average_sentiment)}</strong></div></div><p className="muted">Source counts: {JSON.stringify(data.analytics.source_counts || {})} · Social discussion is experimental and should not be interpreted as fund performance.</p></Panel>{data.fund && <Panel title="Holdings-weighted fund discussion signal"><div className="analysis-grid"><div className="metric"><small>Weighted sentiment</small><strong>{data.fund.weighted_sentiment == null ? "—" : money(data.fund.weighted_sentiment)}</strong></div><div className="metric"><small>Holdings coverage</small><strong>{data.fund.coverage_pct == null ? "—" : `${money(data.fund.coverage_pct)}%`}</strong></div><div className="metric"><small>Disclosure intervals</small><strong>{money((data.fund.intervals || []).length)}</strong></div><div className="metric"><small>Post count</small><strong>{money((data.fund.intervals || []).reduce((total, item) => total + (item.post_count || 0), 0))}</strong></div></div><p className="muted">{data.fund.unavailable_reason || data.fund.warning || "Uses historical equity holdings where available; missing coverage is not inferred."}</p></Panel>}</>}</>}
        {tab === "Assistant" && <><Panel title="Research assistant"><p className="muted">Ask a question. LangGraph routes it to the relevant research specialists; deterministic services calculate financial metrics.</p><div className="field"><label>Question</label><textarea rows="4" value={question} onChange={(e) => setQuestion(e.target.value)} /></div><div className="field"><label className="toggle-label"><input className="toggle-input" type="checkbox" checked={synthesize} onChange={(e) => setSynthesize(e.target.checked)} />Generate an AI narrative (uses the configured LLM API)</label></div><div className="field"><label>Search funds by name (optional)</label><div className="toolbar"><input value={assistantSearch} onChange={(e) => setAssistantSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchAssistantSchemes()} placeholder="Search scheme name, e.g. Parag Parikh Flexi Cap" /><button className="secondary" disabled={busy || assistantSearch.trim().length < 2} onClick={searchAssistantSchemes}>Search</button></div><small className="muted">Select up to 5 schemes. Scheme codes are handled automatically.</small></div>{assistantSelected.length > 0 && <div className="field"><label>Selected funds ({assistantSelected.length}/5)</label><div className="event-list">{assistantSelected.map((scheme) => <article className="event-row" key={scheme.scheme_code}><div><strong>{scheme.scheme_name}</strong><small>{scheme.fund_house || "Fund house unavailable"} · {scheme.scheme_category || "Category unavailable"} · Code {scheme.scheme_code}</small></div><button className="secondary" onClick={() => removeAssistantScheme(scheme.scheme_code)}>Remove</button></article>)}</div></div>}{assistantResults.length > 0 && <div className="table-wrap"><table><thead><tr><th>Scheme</th><th>Fund house</th><th>Category</th><th>Action</th></tr></thead><tbody>{assistantResults.map((scheme) => <tr key={scheme.scheme_code}><td>{scheme.scheme_name}<small>Code {scheme.scheme_code}</small></td><td>{scheme.fund_house || "—"}</td><td>{scheme.scheme_category || "—"}</td><td><button className="secondary" disabled={assistantSelected.some((item) => item.scheme_code === scheme.scheme_code) || assistantSelected.length >= 5} onClick={() => addAssistantScheme(scheme)}>{assistantSelected.some((item) => item.scheme_code === scheme.scheme_code) ? "Added" : "Add"}</button></td></tr>)}</tbody></table></div>}<div className="field-row"><div className="field"><label>Benchmark TRI override (optional)</label><input value={benchmark} onChange={(e) => setBenchmark(e.target.value)} placeholder="Leave blank to use an effective official mapping" /></div><div className="field"><label>Start date</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div><div className="field"><label>End date</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div></div><p className="muted">{benchmarkDescription}</p><button className="primary" disabled={busy} onClick={runAssistant}>{busy ? "Researching…" : "Run research"}</button></Panel>{streamProgress.length > 0 && <Panel title="LangGraph execution"><div className="event-list">{streamProgress.map((step, index) => <article className="event-row" key={`${step.node}-${index}`}><div><strong>{step.node}</strong><small>{step.message}</small></div><b>{step.intents?.join(", ") || "running"}</b></article>)}</div></Panel>}{data && <><Panel title="Research synthesis"><p className="answer">{data.answer}</p><div className="chip-row">{data.intents?.map((intent) => <span className="chip" key={intent}>{intent}</span>)}</div>{data.model_used && <small className="muted">Synthesized with {data.model_used}</small>}</Panel><Panel title="Evidence and citations">{data.citations?.length ? data.citations.map((citation, i) => <div className="citation" key={i}><strong>{String(citation.type || "Source").replaceAll("_", " ")}</strong><small>{citation.title || citation.source_name || citation.source_key || "Evidence record"}</small>{citation.scheme_code && <small>Scheme: {citation.scheme_code}</small>}{citation.nav_date && <small>NAV date: {citation.nav_date} · NAV: {citation.canonical_nav ?? "—"}</small>}{citation.verification_status && <small>Verification: {citation.verification_status}</small>}{citation.retrieved_at && <small>Retrieved: {new Date(citation.retrieved_at).toLocaleString()}</small>}{citation.canonical_url && <a href={citation.canonical_url} target="_blank" rel="noreferrer">Open source</a>}</div>) : <Empty>No source references were returned.</Empty>}</Panel><Panel title="Structured evidence"><details><summary>Show retrieved tool outputs</summary><pre className="json-evidence">{JSON.stringify(data.results, null, 2)}</pre></details></Panel>{data.errors?.length > 0 && <Panel title="Data limitations"><ul>{data.errors.map((e) => <li key={e}>{e}</li>)}</ul></Panel>}</>}</>}
        {["Fund Profile", "Actual Exposure", "Security Intelligence"].includes(tab) && <AdvancedIntelligence tab={tab} schemeCodes={schemeCodes} dateFrom={dateFrom} dateTo={dateTo} />}
        {busy && <div className="loading"><span></span> Working…</div>}{error && <div className="error">{error}</div>}
      </div><footer>Personal workspace · Metrics are deterministic · AI summaries are evidence-bounded</footer></main>
  </div>;
}
