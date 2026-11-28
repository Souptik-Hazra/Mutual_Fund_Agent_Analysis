import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { request, streamRequest } from "./api";
import { buildDocumentSearchPath, isBenchmarkObservationUnavailable } from "./research";
import { isPositiveNumber, isValidDateRange, validateTransactionDraft } from "./validation";
import { ActualExposureView, FundProfileView, SecurityModal } from "./AdvancedIntelligence";

const tabs = ["Overview", "Funds", "Compare", "Portfolio", "Investments", "Assistant"];
const COMPARE_COLORS = ["#c5f06b", "#5ec2f2", "#f6a95b", "#e878b9", "#9f8cf7"];

const money = (value) =>
  value == null ? "—" : Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const percent = (value) => (value == null ? "—" : `${(Number(value) * 100).toFixed(2)}%`);
const localDateString = (value = new Date()) => {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

function PerformanceChart({ series = [] }) {
  const [activeIndex, setActiveIndex] = useState(null);
  const points = series
    .map((point) => ({
      date: Array.isArray(point) ? point[0] : point.date,
      value: Number(Array.isArray(point) ? point[1] : point.value),
    }))
    .filter((point) => Number.isFinite(point.value));
  if (points.length < 2) return null;
  const width = 1000, height = 300, padX = 18, padY = 24;
  const values = points.map((point) => point.value);
  const min = Math.min(...values), max = Math.max(...values);
  const spread = max - min || 1;
  const coords = points.map((point, index) => ({
    ...point,
    x: padX + (index / (points.length - 1)) * (width - padX * 2),
    y: height - padY - ((point.value - min) / spread) * (height - padY * 2),
  }));
  const selected = activeIndex == null ? null : coords[activeIndex];
  const handlePointer = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width) * width;
    const index = Math.max(
      0,
      Math.min(coords.length - 1, Math.round(((x - padX) / (width - padX * 2)) * (coords.length - 1))),
    );
    setActiveIndex(index);
  };
  return (
    <div className="performance-chart">
      <div className="chart-legend">
        <span><i className="legend-up" /> Gain</span>
        <span><i className="legend-down" /> Decline</span>
        <span className="muted">Hover or tap the chart to inspect NAV index</span>
      </div>
      <svg
        className="performance-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Interactive fund performance chart"
        onPointerMove={handlePointer}
        onPointerLeave={() => setActiveIndex(null)}
        onClick={handlePointer}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <line
            key={fraction}
            x1={padX}
            x2={width - padX}
            y1={padY + fraction * (height - padY * 2)}
            y2={padY + fraction * (height - padY * 2)}
            className="chart-gridline"
          />
        ))}
        {coords.slice(1).map((point, index) => (
          <line
            key={index}
            x1={coords[index].x}
            y1={coords[index].y}
            x2={point.x}
            y2={point.y}
            className={point.value >= coords[index].value ? "chart-segment gain" : "chart-segment loss"}
          />
        ))}
        {selected && (
          <>
            <line x1={selected.x} x2={selected.x} y1={padY} y2={height - padY} className="chart-crosshair" />
            <circle cx={selected.x} cy={selected.y} r="6" className="chart-active-point" />
          </>
        )}
        <rect x="0" y="0" width={width} height={height} fill="transparent" />
      </svg>
      <div className="chart-readout" aria-live="polite">
        {selected ? (
          <>
            <strong>{selected.value.toFixed(3)}</strong>
            <span>{selected.date || `Observation ${activeIndex + 1}`}</span>
            <small>
              {activeIndex > 0
                ? `${selected.value >= coords[activeIndex - 1].value ? "+" : ""}${(
                    selected.value - coords[activeIndex - 1].value
                  ).toFixed(3)} vs previous observation`
                : "First observation"}
            </small>
          </>
        ) : (
          <span>Move over the graph to inspect a data point</span>
        )}
      </div>
      <div className="chart-axis">
        <span>{points[0].date || "Start"}</span>
        <span>{points[points.length - 1].date || "Latest"}</span>
      </div>
    </div>
  );
}

function ComparePerformanceChart({ funds = [], nameByCode = {} }) {
  const [activeIndex, setActiveIndex] = useState(null);
  const seriesList = funds
    .map((fund, idx) => ({
      scheme_code: fund.scheme_code,
      label: fund.scheme_name || nameByCode[fund.scheme_code] || `Scheme ${fund.scheme_code}`,
      color: COMPARE_COLORS[idx % COMPARE_COLORS.length],
      points: (fund.base100_series || [])
        .map((pt) => ({
          date: Array.isArray(pt) ? pt[0] : pt.date,
          value: Number(Array.isArray(pt) ? pt[1] : pt.value),
        }))
        .filter((pt) => Number.isFinite(pt.value)),
    }))
    .filter((s) => s.points.length >= 2);
  if (!seriesList.length) return null;
  const allValues = seriesList.flatMap((s) => s.points.map((p) => p.value));
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const spread = max - min || 1;
  const width = 1000, height = 300, padX = 18, padY = 24;
  const count = seriesList[0].points.length;

  const lines = seriesList.map((s) => {
    const coords = s.points.map((pt, i) => ({
      ...pt,
      x: padX + (i / Math.max(1, s.points.length - 1)) * (width - padX * 2),
      y: height - padY - ((pt.value - min) / spread) * (height - padY * 2),
    }));
    return { ...s, coords, path: coords.map((c, i) => `${i === 0 ? "M" : "L"}${c.x},${c.y}`).join(" ") };
  });

  const handlePointer = (event) => {
    const bounds = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - bounds.left) / bounds.width) * width;
    const index = Math.max(
      0,
      Math.min(count - 1, Math.round(((x - padX) / (width - padX * 2)) * (count - 1))),
    );
    setActiveIndex(index);
  };
  const selectedX = activeIndex == null ? null : lines[0]?.coords[activeIndex]?.x;

  return (
    <div className="performance-chart">
      <div className="compare-chart-legend">
        {lines.map((line) => (
          <span className="compare-legend-item" key={line.scheme_code}>
            <i className="compare-legend-swatch" style={{ background: line.color }} />
            {line.label}
          </span>
        ))}
      </div>
      <svg
        className="performance-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Multi-fund base-100 comparison chart"
        onPointerMove={handlePointer}
        onPointerLeave={() => setActiveIndex(null)}
        onClick={handlePointer}
      >
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
          <line
            key={fraction}
            x1={padX}
            x2={width - padX}
            y1={padY + fraction * (height - padY * 2)}
            y2={padY + fraction * (height - padY * 2)}
            className="chart-gridline"
          />
        ))}
        {lines.map((line) => (
          <path key={line.scheme_code} d={line.path} stroke={line.color} className="compare-line" />
        ))}
        {selectedX != null && (
          <line x1={selectedX} x2={selectedX} y1={padY} y2={height - padY} className="chart-crosshair" />
        )}
        <rect x="0" y="0" width={width} height={height} fill="transparent" />
      </svg>
      <div className="chart-readout" aria-live="polite">
        {activeIndex != null ? (
          <>
            <span>{lines[0]?.coords[activeIndex]?.date || `Obs ${activeIndex + 1}`}</span>
            {lines.map((line) => (
              <small key={line.scheme_code} style={{ color: line.color }}>
                {line.label}: {line.coords[activeIndex]?.value?.toFixed(2) ?? "—"}
              </small>
            ))}
          </>
        ) : (
          <span>Hover over the comparison chart to inspect values across all funds</span>
        )}
      </div>
      <div className="chart-axis">
        <span>{seriesList[0].points[0]?.date || "Start"}</span>
        <span>{seriesList[0].points[seriesList[0].points.length - 1]?.date || "Latest"}</span>
      </div>
    </div>
  );
}

function FundSelector({
  selectedSchemes = [],
  onSelect,
  onRemove,
  max = 5,
  label = "Search and select fund by name",
  placeholder = "Type fund name, e.g. Parag Parikh Flexi Cap, HDFC Mid-Cap...",
}) {
  const [term, setTerm] = useState("");
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  useEffect(() => {
    const trimmed = term.trim();
    let active = true;
    if (trimmed.length < 2) {
      setSuggestions([]); setOpen(false); setSearching(false); setSearchError("");
      return () => { active = false; };
    }
    setSearching(true); setSearchError("");
    const handle = setTimeout(() => {
      request(`/schemes?q=${encodeURIComponent(trimmed)}&limit=12`)
        .then((res) => {
          if (!active) return;
          setSuggestions(Array.isArray(res.items) ? res.items : []); setOpen(true);
        })
        .catch((error) => {
          if (!active) return;
          setSuggestions([]); setSearchError(error.message || "Unable to search funds."); setOpen(true);
        })
        .finally(() => { if (active) setSearching(false); });
    }, 220);
    return () => { active = false; clearTimeout(handle); };
  }, [term]);

  return (
    <div className="fund-selector">
      {selectedSchemes.length > 0 && (
        <div className="fund-chips">
          {selectedSchemes.map((s) => (
            <span className="fund-chip" key={s.scheme_code}>
              <span>{s.scheme_name}</span>
              <small>{s.plan_type || ""}</small>
              <button type="button" aria-label={`Remove ${s.scheme_name}`} onClick={() => onRemove(s.scheme_code)}>×</button>
            </span>
          ))}
        </div>
      )}
      <div className="field">
        <label>{label}</label>
        <input value={term} role="combobox" aria-label={label} aria-autocomplete="list" aria-expanded={open}
          onChange={(e) => setTerm(e.target.value)}
          onFocus={() => (suggestions.length || searching || searchError) && setOpen(true)}
          onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }} placeholder={placeholder} />
      </div>
      {open && (searching || searchError || suggestions.length > 0) && (
        <div className="fund-suggestions" role="listbox" aria-label="Fund search results">
          {searching && <div className="fund-search-status">Searching funds…</div>}
          {searchError && <div className="fund-search-error" role="status">{searchError}</div>}
          {!searching && !searchError && suggestions.length === 0 && <div className="fund-search-status">No matching funds found.</div>}
          {suggestions.map((s) => {
            const added = selectedSchemes.some((item) => item.scheme_code === s.scheme_code);
            return (
              <button
                type="button"
                key={s.scheme_code}
                className="fund-suggestion-item"
                disabled={added || (max > 1 && selectedSchemes.length >= max)}
                onClick={() => {
                  onSelect(s);
                  setTerm("");
                  setSuggestions([]);
                  setOpen(false);
                }}
              >
                <div>
                  <strong>{s.scheme_name}</strong>
                  <small>{s.fund_house || "—"} · {s.scheme_category || "—"} · {s.plan_type || "—"} / {s.option_type || "—"}</small>
                </div>
                <span className="link-pill">{added ? "Selected" : "Select"}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function Panel({ title, children, action }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
function Empty({ children = "Run a query to see results." }) {
  return <p className="empty">{children}</p>;
}

export default function App() {
  const [tab, setTab] = useState("Overview");
  const [assistantSubtab, setAssistantSubtab] = useState("chat");
  const [health, setHealth] = useState("Checking API…");
  const [busy, setBusy] = useState(false);
  const [busyStep, setBusyStep] = useState("");
  const [elapsedSec, setElapsedSec] = useState(0);
  const [error, setError] = useState("");
  const [data, setData] = useState(null);

  const [overviewAudit, setOverviewAudit] = useState(null);
  const [overviewCaps, setOverviewCaps] = useState(null);
  const [activeRiskData, setActiveRiskData] = useState(null);
  const [categoryData, setCategoryData] = useState(null);
  const [profileData, setProfileData] = useState(null);
  const [equityStatusData, setEquityStatusData] = useState(null);
  const [equityCompareData, setEquityCompareData] = useState(null);
  const [actualExposureData, setActualExposureData] = useState(null);
  const [modalSecurity, setModalSecurity] = useState(null);
  const closeSecurityModal = useCallback(() => setModalSecurity(null), []);

  const [query, setQuery] = useState("");
  const [codes, setCodes] = useState("125497");
  const [selectedSchemes, setSelectedSchemes] = useState([]);
  const [compareSearch, setCompareSearch] = useState("");
  const [compareResults, setCompareResults] = useState([]);
  const [compareSelected, setCompareSelected] = useState([]);
  const [benchmark, setBenchmark] = useState("");
  const [benchmarkResolution, setBenchmarkResolution] = useState(null);
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
  const [streamProgress, setStreamProgress] = useState([]);
  const [sipAmount, setSipAmount] = useState("5000");
  const [sipDay, setSipDay] = useState("1");
  const [transactionDate, setTransactionDate] = useState(dateTo);
  const [transactionType, setTransactionType] = useState("purchase");
  const [transactionAmount, setTransactionAmount] = useState("5000");
  const [transactionUnits, setTransactionUnits] = useState("100");
  const [transactionNav, setTransactionNav] = useState("");
  const [transactionNotes, setTransactionNotes] = useState("");
  const compareSearchRequest = useRef(0);
  const assistantSearchRequest = useRef(0);
  const eventSearchRequest = useRef(0);
  const operationRequest = useRef(0);

  const schemeCodes = useMemo(
    () =>
      codes
        .split(",")
        .map((x) => Number(x.trim()))
        .filter((x) => Number.isInteger(x) && x > 0),
    [codes],
  );
  const compareNameMap = useMemo(() => Object.fromEntries(selectedSchemes.map((s) => [s.scheme_code, s.scheme_name])), [selectedSchemes]);
  const updateSchemeSelection = (next) => {
    operationRequest.current += 1;
    const unique = [...new Map(next.map((item) => [item.scheme_code, item])).values()].slice(0, 5);
    setSelectedSchemes(unique); setCompareSelected(unique); setAssistantSelected(unique);
    setCodes(unique.map((item) => item.scheme_code).join(","));
    setData(null); setError(""); setBusy(false); setBusyStep("");
  };
  const selectGlobalScheme = (scheme, maxCount = 5) => {
    if (maxCount === 1) return updateSchemeSelection([scheme]);
    if (selectedSchemes.some((item) => item.scheme_code === scheme.scheme_code)) return;
    if (selectedSchemes.length >= maxCount) return setError(`Select a maximum of ${maxCount} funds.`);
    updateSchemeSelection([...selectedSchemes, scheme]);
  };
  const removeGlobalScheme = (schemeCode) => updateSchemeSelection(selectedSchemes.filter((item) => item.scheme_code !== schemeCode));
  const validateDateRange = () => {
    if (!isValidDateRange(dateFrom, dateTo)) {
      setError("Choose valid dates. Start date must be on or before the end date.");
      return false;
    }
    return true;
  };

  useEffect(() => {
    if (!busy) {
      setElapsedSec(0);
      return;
    }
    const started = Date.now();
    const timer = setInterval(() => {
      setElapsedSec(((Date.now() - started) / 1000).toFixed(1));
    }, 200);
    return () => clearInterval(timer);
  }, [busy]);

  useEffect(() => {
    request("/health/live")
      .then(() => {
        setHealth("API connected");
        request("/audit/coverage").then(setOverviewAudit).catch(() => {});
        request("/assistant/capabilities").then(setOverviewCaps).catch(() => {});
      })
      .catch(() => setHealth("API offline"));
  }, []);

  useEffect(() => {
    if (tab === "Assistant" && assistantSubtab === "events" && !eventSources.length) {
      request("/events/sources")
        .then((result) => setEventSources(result.items || []))
        .catch(() => setEventSources([]));
    }
  }, [tab, assistantSubtab]);

  async function resolveBenchmarkForCodes(targetCodes, asOf, override = "") {
    const requestId = operationRequest.current;
    if (override.trim()) {
      const result = {
        availability: "overridden",
        benchmark: { code: override.trim(), source: "niftyindices", source_key: null },
        mappings: [],
      };
      if (requestId === operationRequest.current) setBenchmarkResolution(result);
      return result;
    }
    if (!targetCodes.length) {
      const result = { availability: "unavailable", benchmark: null, mappings: [] };
      if (requestId === operationRequest.current) setBenchmarkResolution(result);
      return result;
    }
    const mappings = await Promise.all(
      targetCodes.map(async (code) => {
        const params = asOf ? "?as_of=" + encodeURIComponent(asOf) : "";
        return await request("/fund-intelligence/schemes/" + code + "/benchmark" + params);
      }),
    );
    const first = mappings[0]?.benchmark;
    const common =
      Boolean(first) &&
      mappings.every(
        (item) =>
          item.availability === "mapped" &&
          item.benchmark?.code === first.code &&
          item.benchmark?.source === first.source &&
          item.benchmark?.source_key === first.source_key,
      );
    const result = {
      availability: common
        ? "mapped"
        : mappings.some((item) => item.availability === "mapped")
          ? "not_common"
          : "unmapped",
      benchmark: common ? first : null,
      mappings,
    };
    if (requestId === operationRequest.current) setBenchmarkResolution(result);
    return result;
  }

  const benchmarkDescription = benchmarkResolution?.benchmark
    ? "Benchmark " +
      benchmarkResolution.benchmark.code +
      " · source " +
      (benchmarkResolution.benchmark.source_name || benchmarkResolution.benchmark.source) +
      " · effective " +
      (benchmarkResolution.benchmark.effective_from || "unknown") +
      " to " +
      (benchmarkResolution.benchmark.effective_to || "open-ended")
    : benchmarkResolution?.availability === "overridden"
      ? "User override: " +
        benchmarkResolution.benchmark.code +
        " · source " +
        benchmarkResolution.benchmark.source
      : benchmarkResolution?.availability === "not_common"
        ? "Selected schemes do not share one effective benchmark mapping; benchmark metrics will be omitted."
        : "No valid official effective-dated mapping; fund-only analysis will be used unless you enter an explicit override.";

  async function run(fn, stepLabel = "") {
    const requestId = ++operationRequest.current;
    setBusy(true); setBusyStep(stepLabel); setError(""); setData(null);
    try {
      const result = await fn();
      if (requestId === operationRequest.current) setData(result);
      return result;
    } catch (e) {
      if (requestId === operationRequest.current) setError(e.message);
      return null;
    } finally {
      if (requestId === operationRequest.current) { setBusy(false); setBusyStep(""); }
    }
  }
  function json(method, body) {
    return { method, body: JSON.stringify(body) };
  }

  const runFunds = () =>
    run(
      () => request(query.trim() ? `/schemes?q=${encodeURIComponent(query.trim())}&limit=30` : "/schemes?limit=30"),
      "Searching local scheme catalogue…",
    );
  const runDiscoverFunds = () => {
    if (query.trim().length < 2) return setError("Enter at least 2 characters to search MFAPI.");
    return run(
      () => request(`/schemes/discover?q=${encodeURIComponent(query.trim())}`),
      "Querying upstream MFAPI directory…",
    );
  };

  const runFundAnalysis = (code) => {
    if (!validateDateRange()) return;
    setCodes(String(code));
    setActiveRiskData(null);
    setCategoryData(null);
    setProfileData(null);
    return run(async () => {
      setBusyStep(`Syncing NAV history for scheme ${code}…`);
      await request("/schemes/" + code + "/sync-nav", { method: "POST" });
      setBusyStep("Resolving benchmark mapping…");
      const selection = await resolveBenchmarkForCodes([code], dateTo, benchmark);
      setBusyStep("Calculating return, risk & drawdown metrics…");
      const params = new URLSearchParams({
        start_date: dateFrom,
        end_date: dateTo,
        frequency: analysisFrequency,
      });
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
          benchmark_unavailable_reason:
            "The effective mapping exists, but its TRI observations were unavailable: " + error.message,
        };
      }
    }, "Preparing analysis…");
  };

  const loadActiveRisk = async (schemeCode, benchmarkCode, benchmarkSource = "niftyindices") => {
    if (!validateDateRange() || !benchmarkCode) return;
    const requestId = ++operationRequest.current;
    setBusy(true);
    setBusyStep("Computing tracking error and information ratio…");
    setError("");
    try {
      const params = new URLSearchParams({
        benchmark_code: benchmarkCode,
        benchmark_source: benchmarkSource,
        start_date: dateFrom,
        end_date: dateTo,
      });
      const result = await request(`/schemes/${schemeCode}/active-risk?${params.toString()}`);
      if (requestId === operationRequest.current) setActiveRiskData(result);
    } catch (e) {
      if (requestId === operationRequest.current) setError(e.message);
    } finally {
      if (requestId === operationRequest.current) { setBusy(false); setBusyStep(""); }
    }
  };

  const runCategoryAnalysis = async (targetCode = schemeCodes[0]) => {
    if (!validateDateRange()) return;
    if (!targetCode) return setError("Enter a valid scheme code first.");
    const requestId = ++operationRequest.current;
    setBusy(true);
    setBusyStep("Ranking category peers on common dates…");
    setError("");
    try {
      const selection = await resolveBenchmarkForCodes([targetCode], dateTo, benchmark);
      const params = new URLSearchParams({ start_date: dateFrom, end_date: dateTo });
      if (selection.benchmark) {
        params.set("benchmark_code", selection.benchmark.code);
        params.set("benchmark_source", selection.benchmark.source);
      }
      const result = await request(`/fund-intelligence/schemes/${targetCode}/category?${params.toString()}`);
      if (requestId === operationRequest.current) setCategoryData({ ...result, benchmark_selection: selection });
    } catch (e) {
      if (requestId === operationRequest.current) setError(e.message);
    } finally {
      if (requestId === operationRequest.current) { setBusy(false); setBusyStep(""); }
    }
  };

  const loadFundProfile = async (targetCode = schemeCodes[0]) => {
    if (!validateDateRange()) return;
    if (!targetCode) return setError("Enter a valid scheme code first.");
    const requestId = ++operationRequest.current;
    setBusy(true);
    setBusyStep("Loading consolidated fund profile…");
    setError("");
    try {
      const params = new URLSearchParams();
      if (dateFrom) params.set("start_date", dateFrom);
      if (dateTo) params.set("end_date", dateTo);
      const result = await request(`/fund-intelligence/schemes/${targetCode}/profile?${params}`);
      if (requestId === operationRequest.current) setProfileData(result);
    } catch (e) {
      if (requestId === operationRequest.current) setError(e.message);
    } finally {
      if (requestId === operationRequest.current) { setBusy(false); setBusyStep(""); }
    }
  };

  const searchCompareSchemes = async () => {
    const requestId = ++compareSearchRequest.current;
    const term = compareSearch.trim();
    if (term.length < 2) return setError("Enter at least 2 characters to search for a scheme.");
    setBusy(true);
    setBusyStep("Searching schemes…");
    setError("");
    try {
      const result = await request("/schemes?q=" + encodeURIComponent(term) + "&limit=30");
      if (requestId !== compareSearchRequest.current) return;
      setCompareResults(result.items || []);
      if (!result.items?.length) setError("No matching schemes found. Try a different name.");
    } catch (e) {
      if (requestId === compareSearchRequest.current) setError(e.message);
    } finally {
      if (requestId === compareSearchRequest.current) { setBusy(false); setBusyStep(""); }
    }
  };
  const addCompareScheme = (scheme) => {
    if (selectedSchemes.some((item) => item.scheme_code === scheme.scheme_code)) return;
    if (selectedSchemes.length >= 5) return setError("You can compare a maximum of 5 schemes.");
    updateSchemeSelection([...selectedSchemes, scheme]);
  };
  const removeCompareScheme = (schemeCode) => updateSchemeSelection(selectedSchemes.filter((item) => item.scheme_code !== schemeCode));
  const runCompare = () => {
    if (!validateDateRange()) return;
    if (schemeCodes.length < 2 || schemeCodes.length > 5) {
      setError("Enter 2 to 5 valid scheme codes, separated by commas, to compare funds.");
      return;
    }
    return run(async () => {
      setBusyStep(`Syncing NAVs for ${schemeCodes.length} funds…`);
      await Promise.all(
        schemeCodes.map((code) => request("/schemes/" + code + "/sync-nav", { method: "POST" })),
      );
      setBusyStep("Resolving common benchmark…");
      const selection = await resolveBenchmarkForCodes(schemeCodes, dateTo, benchmark);
      setBusyStep("Computing aligned multi-fund comparison…");
      const payload = {
        scheme_codes: schemeCodes,
        benchmark_code: selection.benchmark?.code || null,
        benchmark_source: selection.benchmark?.source || "niftyindices",
        start_date: dateFrom,
        end_date: dateTo,
        frequency: analysisFrequency,
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
    }, "Preparing comparison…");
  };

  const runEquityComparison = async () => {
    if (schemeCodes.length < 2 || schemeCodes.length > 5) return setError("Enter two to five scheme codes.");
    const requestId = ++operationRequest.current;
    setBusy(true);
    setBusyStep("Comparing disclosed equity overlap…");
    setError("");
    try {
      const result = await request("/fund-intelligence/compare", json("POST", { scheme_codes: schemeCodes }));
      if (requestId === operationRequest.current) setEquityCompareData(result);
    } catch (e) {
      if (requestId === operationRequest.current) setError(e.message);
    } finally {
      if (requestId === operationRequest.current) { setBusy(false); setBusyStep(""); }
    }
  };

  const runPortfolio = () =>
    run(async () => {
      const asOf = encodeURIComponent(dateTo);
      const snapshot = await request(`/portfolios/${schemeCodes[0]}?as_of=${asOf}`);
      const quality = await request(`/portfolios/${schemeCodes[0]}/quality?as_of=${asOf}`);
      return { ...snapshot, quality };
    }, "Loading portfolio disclosure…");

  const runEquityStatus = async () => {
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    const requestId = ++operationRequest.current;
    setBusy(true);
    setBusyStep("Loading underlying equity status…");
    setError("");
    try {
      const result = await request(`/fund-intelligence/schemes/${schemeCodes[0]}/equity-status?as_of=${encodeURIComponent(dateTo)}`);
      if (requestId === operationRequest.current) setEquityStatusData(result);
    } catch (e) {
      if (requestId === operationRequest.current) setError(e.message);
    } finally {
      if (requestId === operationRequest.current) { setBusy(false); setBusyStep(""); }
    }
  };

  const loadActualExposure = async () => {
    if (!schemeCodes.length) return setError("Enter at least one scheme code.");
    const requestId = ++operationRequest.current;
    setBusy(true);
    setBusyStep("Computing ledger-weighted equity exposure…");
    setError("");
    try {
      const params = new URLSearchParams();
      if (dateTo) params.set("as_of_date", dateTo);
      schemeCodes.forEach((code) => params.append("scheme_codes", String(code)));
      const result = await request(`/fund-intelligence/portfolio/actual-exposure?${params}`);
      if (requestId === operationRequest.current) setActualExposureData(result);
    } catch (e) {
      if (requestId === operationRequest.current) setError(e.message);
    } finally {
      if (requestId === operationRequest.current) { setBusy(false); setBusyStep(""); }
    }
  };

  const searchEventSchemes = async () => {
    const requestId = ++eventSearchRequest.current;
    const term = eventSearch.trim();
    if (term.length < 2) return setError("Enter at least 2 characters to search for a scheme.");
    setBusy(true);
    setError("");
    try {
      const result = await request("/schemes?q=" + encodeURIComponent(term) + "&limit=30");
      if (requestId !== eventSearchRequest.current) return;
      setEventResults(result.items || []);
      if (!result.items?.length) setError("No matching schemes found.");
    } catch (e) {
      if (requestId === eventSearchRequest.current) setError(e.message);
    } finally {
      if (requestId === eventSearchRequest.current) setBusy(false);
    }
  };
  const runEvents = async () => {
    if (!validateDateRange()) return;
    const requestId = ++operationRequest.current;
    const selectedCode = eventScheme?.scheme_code || schemeCodes[0];
    if (!selectedCode) return setError("Search and select a fund before loading events.");
    const params = new URLSearchParams({ start_date: dateFrom, end_date: dateTo, limit: "100" });
    params.set("as_of", new Date(`${dateTo}T23:59:59+05:30`).toISOString());
    if (eventStatus) params.set("status", eventStatus);
    if (eventSource.trim()) params.set("source_key", eventSource.trim());
    setBusy(true);
    setBusyStep("Loading events and historical fund exposure…");
    setError("");
    setEventData(null);
    try {
      const [listing, exposure] = await Promise.all([
        request(`/events?${params.toString()}`),
        request(`/events/fund-exposure/${selectedCode}?start_date=${dateFrom}&end_date=${dateTo}`),
      ]);
      const exposureById = new Map((exposure.events || []).map((item) => [item.event_id, item]));
      if (requestId === operationRequest.current) setEventData({
        ...listing,
        events: (listing.items || []).map((item) => ({ ...item, ...(exposureById.get(item.event_id) || {}) })),
        exposure_summary: exposure,
      });
    } catch (e) {
      if (requestId === operationRequest.current) setError(e.message);
    } finally {
      if (requestId === operationRequest.current) { setBusy(false); setBusyStep(""); }
    }
  };
  const collectEventFeed = async () => {
    const requestId = ++operationRequest.current;
    const source = eventSources.find((item) => item.source_key === eventSource);
    if (!source) return setError("Select an official source before collecting.");
    if (!source.ready) return setError("This source is not approved for collection.");
    if (!eventFeedUrl.trim()) return setError("Enter the verified RSS/Atom feed URL.");
    setBusy(true);
    setBusyStep("Collecting official RSS/Atom feed…");
    setError("");
    setEventCollection(null);
    try {
      const result = await request(
        `/events/collect/${encodeURIComponent(source.source_key)}?feed_url=${encodeURIComponent(eventFeedUrl.trim())}`,
        { method: "POST" },
      );
      if (requestId !== operationRequest.current) return;
      setEventCollection(result);
      const refreshed = await request("/events/sources");
      if (requestId === operationRequest.current) {
        setEventSources(refreshed.items || []);
        await runEvents();
      }
    } catch (e) {
      if (requestId === operationRequest.current) setError(e.message);
    } finally {
      if (requestId === operationRequest.current) { setBusy(false); setBusyStep(""); }
    }
  };

  const runDocuments = () =>
    run(() => request(buildDocumentSearchPath(documentQuery, schemeCodes[0])), "Searching indexed documents…");

  const searchAssistantSchemes = async () => {
    const requestId = ++assistantSearchRequest.current;
    const term = assistantSearch.trim();
    if (term.length < 2) return setError("Enter at least 2 characters to search for a scheme.");
    setBusy(true);
    setError("");
    try {
      const result = await request("/schemes?q=" + encodeURIComponent(term) + "&limit=30");
      if (requestId !== assistantSearchRequest.current) return;
      setAssistantResults(result.items || []);
      if (!result.items?.length) setError("No matching schemes found.");
    } catch (e) {
      if (requestId === assistantSearchRequest.current) setError(e.message);
    } finally {
      if (requestId === assistantSearchRequest.current) setBusy(false);
    }
  };
  const addAssistantScheme = (scheme) => {
    if (selectedSchemes.some((item) => item.scheme_code === scheme.scheme_code)) return;
    if (selectedSchemes.length >= 5) return setError("Select a maximum of 5 schemes.");
    updateSchemeSelection([...selectedSchemes, scheme]);
  };
  const removeAssistantScheme = (schemeCode) => updateSchemeSelection(selectedSchemes.filter((item) => item.scheme_code !== schemeCode));
  async function runAssistant() {
    if (!validateDateRange()) return;
    const requestId = ++operationRequest.current;
    setBusy(true);
    setBusyStep("Syncing NAVs…");
    setError("");
    setData(null);
    setStreamProgress([]);
    try {
      if (schemeCodes.length) {
        await Promise.all(
          schemeCodes.map((code) => request("/schemes/" + code + "/sync-nav", { method: "POST" })),
        );
      }
      setBusyStep("Resolving benchmark mapping…");
      const selection = await resolveBenchmarkForCodes(schemeCodes, dateTo, benchmark);
      setBusyStep("Running LangGraph specialists…");
      const result = await streamRequest(
        "/assistant/research/stream",
        {
          question,
          scheme_codes: schemeCodes,
          benchmark_code: selection.benchmark?.code || null,
          benchmark_source: selection.benchmark?.source || null,
          start_date: dateFrom,
          end_date: dateTo,
          as_of_date: dateTo,
          synthesize,
        },
        (progress) => setStreamProgress((current) => [...current, progress]),
      );
      if (requestId === operationRequest.current) setData(result);
    } catch (e) {
      if (requestId === operationRequest.current) setError(e.message);
    } finally {
      if (requestId === operationRequest.current) { setBusy(false); setBusyStep(""); }
    }
  }

  const runSipSimulation = () => {
    if (!validateDateRange()) return;
    if (!isPositiveNumber(sipAmount)) return setError("Enter a SIP amount greater than zero.");
    if (!Number.isInteger(Number(sipDay)) || Number(sipDay) < 1 || Number(sipDay) > 31) return setError("SIP installment day must be between 1 and 31.");
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    return run(
      () =>
        request(
          `/schemes/${schemeCodes[0]}/sip-simulation`,
          json("POST", {
            start_date: dateFrom,
            end_date: dateTo,
            valuation_date: dateTo,
            monthly_amount: sipAmount,
            day_of_month: Number(sipDay),
          }),
        ),
      "Simulating monthly SIP…",
    );
  };
  const loadTransactions = () => {
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    return run(() => request(`/schemes/${schemeCodes[0]}/transactions`), "Loading ledger…");
  };
  const loadInvestorReturns = () => {
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    return run(() => request(`/schemes/${schemeCodes[0]}/investor-returns`), "Calculating actual XIRR…");
  };
  const addTransaction = () => {
    const validationError = validateTransactionDraft({
      transactionDate, type: transactionType, amount: transactionAmount, units: transactionUnits, nav: transactionNav,
    }, localDateString());
    if (validationError) return setError(validationError);
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    const unitTypes = ["purchase", "sip", "additional_purchase", "redemption", "switch_in", "switch_out"];
    const payload = {
      transaction_date: transactionDate,
      transaction_type: transactionType,
      amount: transactionAmount,
      units: unitTypes.includes(transactionType) ? transactionUnits : null,
      nav: transactionNav ? transactionNav : null,
      notes: transactionNotes.trim() || null,
    };
    return run(async () => {
      await request(`/schemes/${schemeCodes[0]}/transactions`, json("POST", payload));
      setTransactionNotes("");
      return await request(`/schemes/${schemeCodes[0]}/transactions`);
    }, "Saving transaction…");
  };
  const deleteTransaction = (transactionId) => {
    if (!window.confirm(`Delete transaction #${transactionId}? This cannot be undone.`)) return;
    return run(async () => {
      await request(`/transactions/${transactionId}`, { method: "DELETE" });
      return await request(`/schemes/${schemeCodes[0]}/transactions`);
    }, "Deleting transaction…");
  };

  async function importDocument() {
    if (!selectedDocument) return setError("Choose a PDF first.");
    if (!/\.pdf$/i.test(selectedDocument.name) || (selectedDocument.type && selectedDocument.type !== "application/pdf")) return setError("Upload a PDF file only.");
    const form = new FormData();
    form.append("file", selectedDocument);
    form.append("source_key", "amc_disclosures");
    form.append("title", documentTitle || selectedDocument.name);
    if (schemeCodes[0]) form.append("scheme_code", String(schemeCodes[0]));
    const result = await run(() => request("/documents/upload", { method: "POST", body: form }), "Uploading and indexing PDF…");
    if (result) { setSelectedDocument(null); setDocumentTitle(""); const picker = document.getElementById("document-upload-input"); if (picker) picker.value = ""; }
  }
  async function importPortfolio() {
    if (!schemeCodes[0]) return setError("Enter a valid scheme code first.");
    if (!selectedFile) return setError("Choose a normalized AMC CSV or XLSX file first.");
    if (!/\.(csv|xlsx)$/i.test(selectedFile.name)) return setError("Upload a CSV or XLSX file only.");
    const form = new FormData();
    form.append("file", selectedFile);
    form.append("scheme_code", String(schemeCodes[0]));
    form.append("effective_date", dateTo);
    const result = await run(() => request("/portfolios/import-file", { method: "POST", body: form }), "Importing AMC disclosure…");
    if (result) { setSelectedFile(null); const picker = document.getElementById("portfolio-upload-input"); if (picker) picker.value = ""; }
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">MF</span>
          <div>
            <strong>Fund Intelligence</strong>
            <small>Personal research workspace</small>
          </div>
        </div>
        <div className="nav-section-label">Research</div>
        <nav>
          {tabs.map((item) => (
            <button
              key={item}
              className={tab === item ? "nav-item active" : "nav-item"}
              onClick={() => {
                compareSearchRequest.current += 1;
                assistantSearchRequest.current += 1;
                eventSearchRequest.current += 1;
                operationRequest.current += 1;
                setBusy(false);
                setBusyStep("");
                setTab(item);
                setData(null);
                setError("");
                setActiveRiskData(null);
              }}
            >
              {item}
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <span className={health === "API connected" ? "dot online" : "dot"}></span>
          {health}
          <small>Local API · localhost:8000</small>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">INDIA · MUTUAL FUND RESEARCH</p>
            <h1>{tab}</h1>
          </div>
          <div className="top-actions">
            <span className="status-pill">{health}</span>
            <span className="date-label">{new Date().toLocaleDateString("en-IN", { dateStyle: "medium" })}</span>
          </div>
        </header>

        <div className="workspace">
          {tab === "Overview" && (
            <>
              <div className="hero">
                <div>
                  <p className="eyebrow">RESEARCH CONSOLE</p>
                  <h2>Understand funds beyond returns.</h2>
                  <p>Analyse performance, category peers, portfolio exposure, disclosures and events in one streamlined workspace.</p>
                  <button className="primary" onClick={() => setTab("Assistant")}>Start research <span>→</span></button>
                </div>
                <div className="hero-art">
                  <div className="orb orb-one"></div>
                  <div className="orb orb-two"></div>
                  <div className="hero-stat">
                    <small>RESEARCH ENGINE</small>
                    <strong>{overviewCaps?.agents?.length || 8} research specialists</strong>
                    <span>{overviewCaps?.orchestration || "LangGraph"} orchestration</span>
                  </div>
                </div>
              </div>
              <div className="stat-grid">
                <div className="stat-card"><span>01</span><strong>Funds & Peers</strong><small>CAGR · Sharpe · Sortino · Drawdown · Category Rank</small></div>
                <div className="stat-card"><span>02</span><strong>Compare & Overlap</strong><small>Multi-fund chart · Alpha/Beta · Common Holdings</small></div>
                <div className="stat-card"><span>03</span><strong>Portfolio & Stocks</strong><small>AMC Holdings · Sector Weights · Clickable Security Data</small></div>
                <div className="stat-card"><span>04</span><strong>Investments & AI</strong><small>SIP Simulator · Actual XIRR · Ledger Exposure · LangGraph</small></div>
              </div>
              {overviewAudit?.counts && (
                <Panel title="Local database coverage">
                  <div className="analysis-grid">
                    <div className="metric"><small>Schemes</small><strong>{money(overviewAudit.counts.schemes)}</strong></div>
                    <div className="metric"><small>Reconciled NAV dates</small><strong>{money(overviewAudit.counts.reconciled_nav_dates)}</strong></div>
                    <div className="metric"><small>Portfolio snapshots</small><strong>{money(overviewAudit.counts.portfolio_snapshots)}</strong></div>
                    <div className="metric"><small>Market events</small><strong>{money(overviewAudit.counts.market_events)}</strong></div>
                  </div>
                </Panel>
              )}
              <Panel title="Quick start">
                <p className="muted">Search and select funds by name once, then analyse them across all workspace modules.</p>
                <FundSelector
                  selectedSchemes={selectedSchemes}
                  onSelect={(s) => selectGlobalScheme(s, 5)}
                  onRemove={removeGlobalScheme}
                  max={5}
                  label="Select funds by name (up to 5)"
                />
                <div className="field-row">
                  <div className="field"><label>From</label><input type="date" max={dateTo || undefined} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
                  <div className="field"><label>To</label><input type="date" min={dateFrom || undefined} value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
                </div>
              </Panel>
            </>
          )}

          {tab === "Funds" && (
            <>
              <Panel title="Scheme explorer">
                <div className="toolbar">
                  <input
                    placeholder="Search fund name, code or ISIN"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && runFunds()}
                  />
                  <select value={analysisFrequency} onChange={(e) => setAnalysisFrequency(e.target.value)}>
                    <option value="daily">Daily</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="quarterly">Quarterly</option>
                    <option value="yearly">Yearly</option>
                  </select>
                  <button className="primary" disabled={busy} onClick={runFunds}>Search Local</button>
                  <button className="secondary" disabled={busy || query.trim().length < 2} onClick={runDiscoverFunds}>Discover MFAPI</button>
                </div>
                <div className="field-row">
                  <div className="field"><label>Benchmark TRI override (optional)</label><input value={benchmark} onChange={(e) => setBenchmark(e.target.value)} placeholder="Leave blank for official mapping" /></div>
                  <div className="field"><label>From</label><input type="date" max={dateTo || undefined} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
                  <div className="field"><label>To</label><input type="date" min={dateFrom || undefined} value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
                </div>
                {data?.items?.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr><th>Scheme</th><th>Code</th><th>Fund house</th><th>Category</th><th>Plan / Option</th><th>Action</th></tr>
                      </thead>
                      <tbody>
                        {data.items.map((x) => (
                          <tr key={x.scheme_code}>
                            <td>{x.scheme_name}</td>
                            <td>{x.scheme_code}</td>
                            <td>{x.fund_house || "—"}</td>
                            <td>{x.scheme_category || "—"}</td>
                            <td>{x.plan_type || "—"} / {x.option_type || "—"}</td>
                            <td>
                              <button className="text-button" onClick={() => runFundAnalysis(x.scheme_code)}>Analyse</button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty>{data?.scheme_code ? "Analytics loaded below." : data ? "No matching schemes." : "Search your local scheme catalogue or discover from MFAPI."}</Empty>
                )}
              </Panel>
              {data?.scheme_code && (
                <Panel
                  title={`Fund analytics · ${data.scheme_name || compareNameMap[data.scheme_code] || data.scheme_code}`}
                  action={
                    <div className="toolbar">
                      <button className="secondary" disabled={busy} onClick={() => runCategoryAnalysis(data.scheme_code)}>Category Peers</button>
                      <button className="secondary" disabled={busy} onClick={() => loadFundProfile(data.scheme_code)}>Full Profile</button>
                      {data.benchmark_code && (
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => loadActiveRisk(data.scheme_code, data.benchmark_code, data.benchmark_source || "niftyindices")}
                        >
                          Active Risk
                        </button>
                      )}
                    </div>
                  }
                >
                  <div className="analysis-grid">
                    <div className="metric"><small>CAGR (geometric)</small><strong>{percent(data.cagr)}</strong></div>
                    <div className="metric"><small>Absolute return</small><strong>{percent(data.absolute_return)}</strong></div>
                    <div className="metric"><small>Annual volatility</small><strong>{percent(data.risk?.annualized_volatility)}</strong></div>
                    <div className="metric"><small>Max drawdown</small><strong>{percent(data.drawdown?.maximum_drawdown)}</strong></div>
                    <div className="metric"><small>Sharpe ratio</small><strong>{money(data.risk?.sharpe_ratio)}</strong></div>
                    <div className="metric"><small>Sortino ratio</small><strong>{money(data.risk?.sortino_ratio)}</strong></div>
                    <div className="metric"><small>Alpha (ann.)</small><strong>{percent(data.benchmark?.annualized_alpha)}</strong></div>
                    <div className="metric"><small>Beta</small><strong>{money(data.benchmark?.beta)}</strong></div>
                  </div>
                  <p className="muted">
                    Return basis: {data.return_basis || "unknown"} · Sampling: {data.frequency || "daily"} · {data.observation_count} obs · {data.start_date} to {data.end_date}
                  </p>
                  {data.drawdown && (
                    <p className="muted">
                      Drawdown window: peak {data.drawdown.drawdown_start || "—"} → trough {data.drawdown.drawdown_end || "—"} · duration {data.drawdown.drawdown_duration_days ?? "—"} days · recovery {data.drawdown.recovery_date || "not yet recovered"}
                    </p>
                  )}
                  {data.benchmark_selection && <p className="muted">{benchmarkDescription}</p>}
                  {data.base100_series?.length > 1 && <PerformanceChart series={data.base100_series} />}
                  {activeRiskData && (
                    <div className="profile-section">
                      <h3>Active Risk vs {activeRiskData.benchmark_code}</h3>
                      <div className="analysis-grid">
                        <div className="metric"><small>Tracking error</small><strong>{percent(activeRiskData.tracking_error)}</strong></div>
                        <div className="metric"><small>Information ratio</small><strong>{money(activeRiskData.information_ratio)}</strong></div>
                        <div className="metric"><small>Mean active return</small><strong>{percent(activeRiskData.mean_active_return)}</strong></div>
                        <div className="metric"><small>Aligned obs</small><strong>{activeRiskData.aligned_observation_count}</strong></div>
                      </div>
                    </div>
                  )}
                  {data.rolling_returns?.length > 0 && (
                    <div className="profile-section">
                      <h3>Trailing / Rolling Returns</h3>
                      <div className="table-wrap">
                        <table>
                          <thead><tr><th>Period</th><th>Start</th><th>End</th><th>Return</th><th>Annualized</th></tr></thead>
                          <tbody>
                            {data.rolling_returns.map((r, i) => (
                              <tr key={i}><td>{r.label}</td><td>{r.start_date}</td><td>{r.end_date}</td><td>{percent(r.absolute_return)}</td><td>{percent(r.cagr)}</td></tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                  {data.calendar_year_returns?.length > 0 && (
                    <div className="profile-section">
                      <h3>Calendar Year Returns</h3>
                      <div className="metric-grid-compact">
                        {data.calendar_year_returns.map(([yr, val]) => (
                          <div className="metric" key={yr}><small>{yr}</small><strong>{percent(val)}</strong></div>
                        ))}
                      </div>
                    </div>
                  )}
                </Panel>
              )}
              {categoryData?.selected_fund && (
                <Panel title={`Category peers · ${categoryData.category}`}>
                  <div className="analysis-grid">
                    <div className="metric"><small>Peer count</small><strong>{categoryData.peer_count}</strong></div>
                    <div className="metric"><small>CAGR rank</small><strong>{categoryData.selected_fund.cagr_rank ?? "—"} / {categoryData.peer_count}</strong></div>
                    <div className="metric"><small>CAGR percentile</small><strong>{categoryData.selected_fund.cagr_percentile == null ? "—" : `${money(categoryData.selected_fund.cagr_percentile)}%`}</strong></div>
                    <div className="metric"><small>Sharpe rank</small><strong>{categoryData.selected_fund.sharpe_ratio_rank ?? "—"} / {categoryData.peer_count}</strong></div>
                  </div>
                  <div className="table-wrap peer-table-wrap">
                    <table className="peer-table">
                      <thead>
                        <tr><th>Scheme</th><th>CAGR</th><th>Volatility</th><th>Sharpe</th><th>Max drawdown</th><th>Benchmark TRI</th><th>Alpha</th><th>Beta</th><th>Rank</th></tr>
                      </thead>
                      <tbody>
                        {categoryData.peers?.map((peer) => (
                          <tr key={peer.scheme_code}>
                            <td className="peer-scheme-cell">
                              <strong>{peer.scheme_name}</strong>
                              <small>Code {peer.scheme_code} · {peer.fund_house || "—"}</small>
                            </td>
                            <td>{percent(peer.cagr)}</td>
                            <td>{percent(peer.annualized_volatility)}</td>
                            <td>{money(peer.sharpe_ratio)}</td>
                            <td>{percent(peer.maximum_drawdown)}</td>
                            <td>{percent(peer.benchmark?.annualized_benchmark_return)}</td>
                            <td>{percent(peer.benchmark?.annualized_alpha)}</td>
                            <td>{money(peer.benchmark?.beta)}</td>
                            <td>{peer.cagr_rank ?? "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              )}
              {profileData && (
                <Panel title={`Consolidated Fund Profile · ${profileData.scheme?.scheme_code || ""}`}>
                  <FundProfileView data={profileData} />
                </Panel>
              )}
            </>
          )}

          {tab === "Compare" && (
            <>
              <Panel title="Fund comparison & holdings overlap">
                <div className="field">
                  <label>Search and select 2–5 funds by name</label>
                  <div className="toolbar">
                    <input
                      value={compareSearch}
                      onChange={(e) => setCompareSearch(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && searchCompareSchemes()}
                      placeholder="Search scheme name, e.g. Axis Corporate Bond"
                    />
                    <button className="secondary" disabled={busy || compareSearch.trim().length < 2} onClick={searchCompareSchemes}>Search</button>
                  </div>
                </div>
                {compareSelected.length > 0 && (
                  <div className="field">
                    <label>Selected funds ({compareSelected.length}/5)</label>
                    <div className="event-list">
                      {compareSelected.map((scheme) => (
                        <article className="event-row" key={scheme.scheme_code}>
                          <div>
                            <strong>{scheme.scheme_name}</strong>
                            <small>{scheme.fund_house || "—"} · {scheme.scheme_category || "—"} · Code {scheme.scheme_code}</small>
                          </div>
                          <button className="secondary" onClick={() => removeCompareScheme(scheme.scheme_code)}>Remove</button>
                        </article>
                      ))}
                    </div>
                  </div>
                )}
                {compareResults.length > 0 && (
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>Scheme</th><th>Fund house</th><th>Category</th><th>Action</th></tr></thead>
                      <tbody>
                        {compareResults.map((scheme) => (
                          <tr key={scheme.scheme_code}>
                            <td>{scheme.scheme_name}<small>Code {scheme.scheme_code}</small></td>
                            <td>{scheme.fund_house || "—"}</td>
                            <td>{scheme.scheme_category || "—"}</td>
                            <td>
                              <button
                                className="secondary"
                                disabled={compareSelected.some((item) => item.scheme_code === scheme.scheme_code) || compareSelected.length >= 5}
                                onClick={() => addCompareScheme(scheme)}
                              >
                                {compareSelected.some((item) => item.scheme_code === scheme.scheme_code) ? "Added" : "Add"}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <div className="field-row">
                  <div className="field"><label>Benchmark TRI override (optional)</label><input value={benchmark} onChange={(e) => setBenchmark(e.target.value)} placeholder="Leave blank to use a common verified mapping" /></div>
                  <div className="field"><label>Start date</label><input type="date" max={dateTo || undefined} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
                  <div className="field"><label>End date</label><input type="date" min={dateFrom || undefined} value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
                  <div className="field">
                    <label>Return frequency</label>
                    <select value={analysisFrequency} onChange={(e) => setAnalysisFrequency(e.target.value)}>
                      <option value="daily">Daily</option>
                      <option value="weekly">Weekly</option>
                      <option value="monthly">Monthly</option>
                      <option value="quarterly">Quarterly</option>
                      <option value="yearly">Yearly</option>
                    </select>
                  </div>
                </div>
                <p className="muted">{benchmarkDescription}</p>
                <div className="toolbar">
                  <button className="primary" disabled={busy || schemeCodes.length < 2} onClick={runCompare}>Compare Performance & Risk</button>
                  <button className="secondary" disabled={busy || schemeCodes.length < 2 || schemeCodes.length > 5} onClick={runEquityComparison}>Compare Holdings Overlap</button>
                </div>
              </Panel>
              {data?.funds && (
                <Panel title="Performance & Risk Comparison">
                  <ComparePerformanceChart funds={data.funds} nameByCode={compareNameMap} />
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr><th>Scheme</th><th>Return basis</th><th>Abs. return</th><th>CAGR</th><th>Volatility</th><th>Sharpe</th><th>Sortino</th><th>Max drawdown</th><th>Alpha</th><th>Beta</th></tr>
                      </thead>
                      <tbody>
                        {data.funds.map((f) => (
                          <tr key={f.scheme_code}>
                            <td>
                              {f.scheme_name || compareNameMap[f.scheme_code] || f.scheme_code}
                              {(f.scheme_name || compareNameMap[f.scheme_code]) && <small>Code {f.scheme_code}</small>}
                            </td>
                            <td>{f.return_basis || "unknown"}</td>
                            <td>{percent(f.absolute_return)}</td>
                            <td>{percent(f.cagr)}</td>
                            <td>{percent(f.risk?.annualized_volatility)}</td>
                            <td>{money(f.risk?.sharpe_ratio)}</td>
                            <td>{money(f.risk?.sortino_ratio)}</td>
                            <td>{percent(f.drawdown?.maximum_drawdown)}</td>
                            <td>{percent(f.benchmark?.annualized_alpha)}</td>
                            <td>{money(f.benchmark?.beta)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {data.funds[0]?.calendar_year_returns?.length > 0 && (
                    <div className="profile-section">
                      <h3>Calendar Year Comparison</h3>
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>Year</th>
                              {data.funds.map((f) => <th key={f.scheme_code}>{f.scheme_name || compareNameMap[f.scheme_code] || f.scheme_code}</th>)}
                            </tr>
                          </thead>
                          <tbody>
                            {data.funds[0].calendar_year_returns.map(([yr]) => (
                              <tr key={yr}>
                                <td>{yr}</td>
                                {data.funds.map((f) => {
                                  const match = (f.calendar_year_returns || []).find(([y]) => y === yr);
                                  return <td key={f.scheme_code}>{match ? percent(match[1]) : "—"}</td>;
                                })}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                  <p className="muted">{data.observation_count} common observations · {data.frequency || analysisFrequency} sampling · {data.start_date} to {data.end_date}</p>
                </Panel>
              )}
              {equityCompareData?.pairwise_overlap && (
                <Panel title="Multi-fund equity overlap">
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>Fund A</th><th>Fund B</th><th>Overlap</th><th>Common shares</th></tr></thead>
                      <tbody>
                        {equityCompareData.pairwise_overlap.map((pair) => {
                          const fundA = equityCompareData.funds?.find((f) => f.scheme_code === pair.scheme_a);
                          const fundB = equityCompareData.funds?.find((f) => f.scheme_code === pair.scheme_b);
                          return (
                            <tr key={`${pair.scheme_a}-${pair.scheme_b}`}>
                              <td>{fundA?.scheme_name || compareNameMap[pair.scheme_a] || pair.scheme_a}</td>
                              <td>{fundB?.scheme_name || compareNameMap[pair.scheme_b] || pair.scheme_b}</td>
                              <td>{money(pair.overlap_pct)}% {pair.overlap_is_lower_bound ? "(lower bound)" : ""}</td>
                              <td>{pair.common_security_count}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <div className="profile-section">
                    <h3>Equal-weighted combined exposure (click a stock to inspect)</h3>
                    <div className="table-wrap">
                      <table>
                        <thead><tr><th>Underlying share</th><th>Funds present</th><th>Combined exposure</th></tr></thead>
                        <tbody>
                          {equityCompareData.aggregated_equity_exposure?.slice(0, 30).map((item) => (
                            <tr
                              key={item.security_key}
                              className="clickable-row" tabIndex={0} aria-label={`Inspect ${item.name}`}
                              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setModalSecurity({ key: item.security_key, name: item.name }); } }}
                              onClick={() => setModalSecurity({ key: item.security_key, name: item.name })}
                            >
                              <td>{item.name}<small>{item.security_key}</small></td>
                              <td>{item.funds_present}</td>
                              <td>{money(item.equal_weight_exposure_pct)}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </Panel>
              )}
            </>
          )}

          {tab === "Portfolio" && (
            <>
              <Panel title="Portfolio holdings & underlying stock health">
                <FundSelector
                  selectedSchemes={selectedSchemes.slice(0, 1)}
                  onSelect={(s) => selectGlobalScheme(s, 1)}
                  onRemove={removeGlobalScheme}
                  max={1}
                  label="Select fund by name"
                />
                <div className="toolbar">
                  <button className="primary" disabled={busy || !schemeCodes[0]} onClick={runPortfolio}>Load holdings</button>
                  <button className="secondary" disabled={busy || !schemeCodes[0]} onClick={runEquityStatus}>Check underlying equities</button>
                </div>
                <div className="toolbar upload">
                  <input id="portfolio-upload-input" type="file" accept=".csv,.xlsx" onChange={(e) => setSelectedFile(e.target.files?.[0] || null)} />
                  {selectedFile && <span className="upload-selected">Selected: {selectedFile.name}</span>}
                  <button className="secondary" disabled={busy || !selectedFile} onClick={importPortfolio}>Import disclosure</button>
                </div>
              </Panel>
              {data?.holdings && (
                <Panel title={`Holdings · effective ${data.effective_date}`}>
                  <p className="muted">Click any holding row to inspect its live market quote, dated fundamentals, and corporate events.</p>
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>Security</th><th>Asset class</th><th>Sector</th><th>Weight</th></tr></thead>
                      <tbody>
                        {data.holdings.slice(0, 30).map((h, i) => (
                          <tr
                            key={i}
                            className={h.security_key || h.isin ? "clickable-row" : ""}
                            tabIndex={h.security_key || h.isin ? 0 : undefined}
                            aria-label={h.security_key || h.isin ? `Inspect ${h.security_name}` : undefined}
                            onKeyDown={(e) => { if ((h.security_key || h.isin) && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); setModalSecurity({ key: h.isin || h.security_key, name: h.security_name }); } }}
                            onClick={() => (h.security_key || h.isin) && setModalSecurity({ key: h.isin || h.security_key, name: h.security_name })}
                          >
                            <td>{h.security_name}{(h.isin || h.security_key) && <small>{h.isin || h.security_key}</small>}</td>
                            <td>{h.asset_class}</td>
                            <td>{h.sector || "—"}</td>
                            <td>{h.weight_pct == null ? "—" : `${h.weight_pct}%`}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <p className="muted">Weight coverage: {money(data.weight_coverage_pct)}% · HHI: {money(data.hhi_0_to_1)}</p>
                  <div className="allocation-list">
                    {data.sector_allocation?.slice(0, 10).map((sector) => (
                      <div className="allocation-row" key={sector.sector}>
                        <span>{sector.sector}</span>
                        <div className="allocation-track">
                          <i style={{ width: `${Math.max(0, Math.min(100, Number(sector.weight_pct)))}%` }} />
                        </div>
                        <b>{money(sector.weight_pct)}%</b>
                      </div>
                    ))}
                  </div>
                </Panel>
              )}
              {equityStatusData?.items && (
                <Panel title={`Underlying equity market status · as of ${equityStatusData.holdings_as_of}`}>
                  <div className="analysis-grid">
                    <div className="metric"><small>Equity securities</small><strong>{equityStatusData.equity_security_count}</strong></div>
                    <div className="metric"><small>Market observations</small><strong>{equityStatusData.market_data_available_count}</strong></div>
                  </div>
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>Security</th><th>Fund weight</th><th>Last price</th><th>Day change</th><th>Market status</th><th>Freshness</th></tr></thead>
                      <tbody>
                        {equityStatusData.items.map((item) => (
                          <tr
                            key={item.security_key}
                            className="clickable-row" tabIndex={0} aria-label={`Inspect ${item.security_name}`}
                            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setModalSecurity({ key: item.isin || item.security_key, name: item.security_name }); } }}
                            onClick={() => setModalSecurity({ key: item.isin || item.security_key, name: item.security_name })}
                          >
                            <td>{item.security_name}<small>{item.isin || item.security_key}</small></td>
                            <td>{item.disclosed_weight_pct == null ? "—" : `${money(item.disclosed_weight_pct)}%`}</td>
                            <td>{item.market_data ? `₹${money(item.market_data.last_price)}` : "Unavailable"}</td>
                            <td className={item.market_data?.change_pct > 0 ? "pos" : item.market_data?.change_pct < 0 ? "neg" : ""}>
                              {item.market_data?.change_pct == null ? "—" : `${money(item.market_data.change_pct)}%`}
                            </td>
                            <td>{item.market_data?.market_status || "—"}</td>
                            <td>{item.freshness || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              )}
            </>
          )}

          {tab === "Investments" && (
            <>
              <Panel title="Investment inputs">
                <p className="muted">Simulated SIPs are hypothetical; ledger XIRR and Actual Portfolio Exposure use transactions you enter.</p>
                <FundSelector
                  selectedSchemes={selectedSchemes}
                  onSelect={(s) => selectGlobalScheme(s, 5)}
                  onRemove={removeGlobalScheme}
                  max={5}
                  label="Select fund(s) by name"
                />
                <div className="field-row">
                  <div className="field"><label>Start date</label><input type="date" max={dateTo || undefined} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
                  <div className="field"><label>End / valuation date</label><input type="date" min={dateFrom || undefined} value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
                </div>
              </Panel>
              <Panel title="Historical SIP simulation">
                <div className="field-row">
                  <div className="field"><label>Monthly amount (₹)</label><input type="number" min="0.01" step="0.01" value={sipAmount} onChange={(e) => setSipAmount(e.target.value)} /></div>
                  <div className="field"><label>Installment day (1–31)</label><input type="number" min="1" max="31" value={sipDay} onChange={(e) => setSipDay(e.target.value)} /></div>
                </div>
                <button className="primary" disabled={busy || !schemeCodes[0]} onClick={runSipSimulation}>Simulate SIP</button>
                {data?.return_basis === "simulated_sip" && (
                  <>
                    <div className="analysis-grid">
                      <div className="metric"><small>Invested</small><strong>₹{money(data.invested_amount)}</strong></div>
                      <div className="metric"><small>Current value</small><strong>₹{money(data.current_value)}</strong></div>
                      <div className="metric"><small>Absolute gain</small><strong>₹{money(data.absolute_gain)}</strong></div>
                      <div className="metric"><small>Simulated XIRR</small><strong>{percent(data.xirr)}</strong></div>
                    </div>
                    <div className="table-wrap">
                      <table>
                        <thead><tr><th>Due date</th><th>Amount</th><th>NAV</th><th>Units</th><th>Status</th></tr></thead>
                        <tbody>
                          {data.installments.map((item) => (
                            <tr key={item.due_date}><td>{item.due_date}</td><td>₹{money(item.amount)}</td><td>{item.nav ?? "—"}</td><td>{money(item.units)}</td><td>{item.status}</td></tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}
              </Panel>
              <Panel title="Actual investor transaction ledger & exposure">
                <div className="field-row">
                  <div className="field"><label>Transaction date</label><input type="date" max={localDateString()} value={transactionDate} onChange={(e) => setTransactionDate(e.target.value)} /></div>
                  <div className="field">
                    <label>Transaction type</label>
                    <select value={transactionType} onChange={(e) => setTransactionType(e.target.value)}>
                      <option value="purchase">Purchase</option>
                      <option value="sip">SIP</option>
                      <option value="additional_purchase">Additional purchase</option>
                      <option value="redemption">Redemption</option>
                      <option value="switch_in">Switch in</option>
                      <option value="switch_out">Switch out</option>
                      <option value="dividend_payout">Dividend payout</option>
                      <option value="charges">Charges</option>
                      <option value="tax">Tax</option>
                    </select>
                  </div>
                </div>
                <div className="field-row">
                  <div className="field"><label>Amount (₹)</label><input type="number" min="0.01" step="0.01" value={transactionAmount} onChange={(e) => setTransactionAmount(e.target.value)} /></div>
                  {["purchase", "sip", "additional_purchase", "redemption", "switch_in", "switch_out"].includes(transactionType) && (
                    <div className="field"><label>Units</label><input type="number" min="0.00000001" step="0.00000001" value={transactionUnits} onChange={(e) => setTransactionUnits(e.target.value)} /></div>
                  )}
                  {["purchase", "sip", "additional_purchase", "redemption", "switch_in", "switch_out"].includes(transactionType) && (
                    <div className="field"><label>Optional NAV</label><input type="number" min="0.00000001" step="0.00000001" value={transactionNav} onChange={(e) => setTransactionNav(e.target.value)} /></div>
                  )}
                </div>
                <div className="field"><label>Notes</label><input value={transactionNotes} onChange={(e) => setTransactionNotes(e.target.value)} placeholder="Optional transaction note" /></div>
                <div className="toolbar">
                  <button className="primary" disabled={busy || !schemeCodes[0]} onClick={addTransaction}>Save transaction</button>
                  <button className="secondary" disabled={busy || !schemeCodes[0]} onClick={loadTransactions}>Refresh ledger</button>
                  <button className="secondary" disabled={busy || !schemeCodes[0]} onClick={loadInvestorReturns}>Calculate XIRR</button>
                  <button className="secondary" disabled={busy || !schemeCodes.length} onClick={loadActualExposure}>Actual Stock Exposure</button>
                </div>
                {Array.isArray(data) && (
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>Date</th><th>Type</th><th>Amount</th><th>Units</th><th>NAV</th><th>Action</th></tr></thead>
                      <tbody>
                        {data.map((item) => (
                          <tr key={item.transaction_id}>
                            <td>{item.transaction_date}</td>
                            <td>{item.transaction_type}</td>
                            <td>₹{money(item.amount)}</td>
                            <td>{item.units == null ? "—" : money(item.units)}</td>
                            <td>{item.nav ?? "—"}</td>
                            <td><button className="btn-danger" disabled={busy} onClick={() => deleteTransaction(item.transaction_id)}>Delete</button></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {!data.length && <Empty>No transactions have been entered for this scheme.</Empty>}
                  </div>
                )}
                {data?.return_basis === "actual_ledger" && (
                  <div className="profile-section">
                    <h3>Actual Investor Returns</h3>
                    <div className="analysis-grid">
                      <div className="metric"><small>Cash invested</small><strong>₹{money(data.cash_invested)}</strong></div>
                      <div className="metric"><small>Realized proceeds</small><strong>₹{money(data.realized_proceeds)}</strong></div>
                      <div className="metric"><small>Current value</small><strong>₹{money(data.current_value)}</strong></div>
                      <div className="metric"><small>Actual XIRR</small><strong>{percent(data.xirr)}</strong></div>
                    </div>
                  </div>
                )}
                {actualExposureData && (
                  <div className="profile-section">
                    <h3>Actual Portfolio Exposure</h3>
                    <ActualExposureView
                      data={actualExposureData}
                      dateTo={dateTo}
                      onSelectSecurity={(key, name) => setModalSecurity({ key, name })}
                    />
                  </div>
                )}
              </Panel>
            </>
          )}

          {tab === "Assistant" && (
            <>
              <div className="subtabs">
                <button className={assistantSubtab === "chat" ? "subtab active" : "subtab"} onClick={() => setAssistantSubtab("chat")}>AI Research Chat</button>
                <button className={assistantSubtab === "events" ? "subtab active" : "subtab"} onClick={() => setAssistantSubtab("events")}>Events & Feeds</button>
                <button className={assistantSubtab === "docs" ? "subtab active" : "subtab"} onClick={() => setAssistantSubtab("docs")}>PDF Documents</button>
              </div>

              {assistantSubtab === "chat" && (
                <>
                  <Panel title="Research assistant">
                    <p className="muted">LangGraph routes your question to the relevant specialists; deterministic services calculate all metrics.</p>
                    <div className="field"><label>Question</label><textarea rows="4" value={question} onChange={(e) => setQuestion(e.target.value)} /></div>
                    <div className="field">
                      <label className="toggle-label">
                        <input className="toggle-input" type="checkbox" checked={synthesize} onChange={(e) => setSynthesize(e.target.checked)} />
                        Generate an AI narrative (uses the configured LLM API)
                      </label>
                    </div>
                    <div className="field">
                      <label>Search funds by name (optional)</label>
                      <div className="toolbar">
                        <input
                          value={assistantSearch}
                          onChange={(e) => setAssistantSearch(e.target.value)}
                          onKeyDown={(e) => e.key === "Enter" && searchAssistantSchemes()}
                          placeholder="Search scheme name, e.g. Parag Parikh Flexi Cap"
                        />
                        <button className="secondary" disabled={busy || assistantSearch.trim().length < 2} onClick={searchAssistantSchemes}>Search</button>
                      </div>
                    </div>
                    {assistantSelected.length > 0 && (
                      <div className="event-list">
                        {assistantSelected.map((scheme) => (
                          <article className="event-row" key={scheme.scheme_code}>
                            <div><strong>{scheme.scheme_name}</strong><small>Code {scheme.scheme_code}</small></div>
                            <button className="secondary" onClick={() => removeAssistantScheme(scheme.scheme_code)}>Remove</button>
                          </article>
                        ))}
                      </div>
                    )}
                    {assistantResults.length > 0 && (
                      <div className="table-wrap">
                        <table>
                          <thead><tr><th>Scheme</th><th>Fund house</th><th>Category</th><th>Action</th></tr></thead>
                          <tbody>
                            {assistantResults.map((scheme) => (
                              <tr key={scheme.scheme_code}>
                                <td>{scheme.scheme_name}<small>Code {scheme.scheme_code}</small></td>
                                <td>{scheme.fund_house || "—"}</td>
                                <td>{scheme.scheme_category || "—"}</td>
                                <td>
                                  <button
                                    className="secondary"
                                    disabled={assistantSelected.some((item) => item.scheme_code === scheme.scheme_code) || assistantSelected.length >= 5}
                                    onClick={() => addAssistantScheme(scheme)}
                                  >
                                    {assistantSelected.some((item) => item.scheme_code === scheme.scheme_code) ? "Added" : "Add"}
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    <div className="field-row">
                      <div className="field"><label>Benchmark TRI override (optional)</label><input value={benchmark} onChange={(e) => setBenchmark(e.target.value)} placeholder="Leave blank for official mapping" /></div>
                      <div className="field"><label>Start date</label><input type="date" max={dateTo || undefined} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
                      <div className="field"><label>End date</label><input type="date" min={dateFrom || undefined} value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
                    </div>
                    <p className="muted">{benchmarkDescription}</p>
                    <button className="primary" disabled={busy} onClick={runAssistant}>{busy ? `Researching… (${elapsedSec}s)` : "Run research"}</button>
                  </Panel>
                  {streamProgress.length > 0 && (
                    <Panel title="LangGraph execution">
                      <div className="event-list">
                        {streamProgress.map((step, index) => (
                          <article className="event-row" key={`${step.node}-${index}`}>
                            <div><strong>{step.node}</strong><small>{step.message}</small></div>
                            <b>{step.intents?.join(", ") || "running"}</b>
                          </article>
                        ))}
                      </div>
                    </Panel>
                  )}
                  {data && (
                    <>
                      <Panel title="Research synthesis">
                        <p className="answer">{data.answer}</p>
                        <div className="chip-row">
                          {data.intents?.map((intent) => {
                            const status = data.specialist_statuses?.[intent];
                            const ms = data.specialist_timings_ms?.[intent];
                            return (
                              <span className="chip" key={intent}>
                                {intent}{status ? `: ${status}` : ""}{ms != null ? ` (${ms} ms)` : ""}
                              </span>
                            );
                          })}
                        </div>
                        {data.model_used && <small className="muted">Synthesized with {data.model_used}</small>}
                      </Panel>
                      <Panel title="Evidence and citations">
                        {data.citations?.length ? (
                          data.citations.map((citation, i) => (
                            <div className="citation" key={i}>
                              <strong>{String(citation.type || "Source").replaceAll("_", " ")}</strong>
                              <small>{citation.title || citation.source_name || citation.source_key || "Evidence record"}</small>
                              {citation.scheme_code && <small>Scheme: {citation.scheme_code}</small>}
                              {citation.canonical_url && <a href={citation.canonical_url} target="_blank" rel="noreferrer">Open source</a>}
                            </div>
                          ))
                        ) : (
                          <Empty>No source references were returned.</Empty>
                        )}
                      </Panel>
                      <Panel title="Structured evidence">
                        <details>
                          <summary>Show retrieved tool outputs</summary>
                          <pre className="json-evidence">{JSON.stringify(data.results, null, 2)}</pre>
                        </details>
                      </Panel>
                    </>
                  )}
                </>
              )}

              {assistantSubtab === "events" && (
                <Panel title="Event and news intelligence">
                  <div className="field">
                    <label>Search fund by name</label>
                    <div className="toolbar">
                      <input value={eventSearch} onChange={(e) => setEventSearch(e.target.value)} onKeyDown={(e) => e.key === "Enter" && searchEventSchemes()} placeholder="Search scheme name" />
                      <button className="secondary" disabled={busy || eventSearch.trim().length < 2} onClick={searchEventSchemes}>Search</button>
                    </div>
                  </div>
                  {eventScheme && (
                    <div className="event-row">
                      <div><strong>{eventScheme.scheme_name}</strong><small>Code {eventScheme.scheme_code}</small></div>
                      <button className="secondary" onClick={() => setEventScheme(null)}>Change fund</button>
                    </div>
                  )}
                  {eventResults.length > 0 && (
                    <div className="table-wrap">
                      <table>
                        <thead><tr><th>Scheme</th><th>Fund house</th><th>Action</th></tr></thead>
                        <tbody>
                          {eventResults.map((scheme) => (
                            <tr key={scheme.scheme_code}>
                              <td>{scheme.scheme_name}</td>
                              <td>{scheme.fund_house || "—"}</td>
                              <td><button className="secondary" onClick={() => { setEventScheme(scheme); setEventResults([]); }}>Select</button></td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  <div className="field-row">
                    <div className="field"><label>From</label><input type="date" max={dateTo || undefined} value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></div>
                    <div className="field"><label>To</label><input type="date" min={dateFrom || undefined} value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></div>
                    <div className="field">
                      <label>Status</label>
                      <select value={eventStatus} onChange={(e) => setEventStatus(e.target.value)}>
                        <option value="">All statuses</option>
                        {["confirmed", "scheduled", "reported", "unverified", "speculative", "disproved", "outdated"].map((v) => <option key={v}>{v}</option>)}
                      </select>
                    </div>
                  </div>
                  <div className="field-row">
                    <div className="field">
                      <label>Official source</label>
                      <select
                        value={eventSource}
                        onChange={(e) => {
                          setEventSource(e.target.value);
                          const src = eventSources.find((i) => i.source_key === e.target.value);
                          setEventFeedUrl(src?.feed_url || "");
                        }}
                      >
                        <option value="">Select source</option>
                        {eventSources.map((s) => <option key={s.source_key} value={s.source_key}>{s.display_name || s.source_key}</option>)}
                      </select>
                    </div>
                    <div className="field"><label>Verified RSS/Atom feed URL</label><input value={eventFeedUrl} onChange={(e) => setEventFeedUrl(e.target.value)} placeholder="https://official-domain.example/feed.xml" /></div>
                  </div>
                  <div className="toolbar">
                    <button className="secondary" disabled={busy || !eventSource} onClick={collectEventFeed}>Collect official events</button>
                    <button className="primary" disabled={busy} onClick={runEvents}>Load events & fund exposure</button>
                  </div>
                  {eventCollection && <p className="muted">Fetched {eventCollection.fetched} · new {eventCollection.created} · refreshed {eventCollection.updated}</p>}
                  {eventData?.events?.length ? (
                    <div className="event-list">
                      {eventData.events.map((event) => (
                        <article className="event-row" key={event.event_id}>
                          <div>
                            <strong>{event.title}</strong>
                            <small>{event.event_date || "—"} · {event.status} · {event.source_key || "—"}</small>
                            {event.canonical_url && <a href={event.canonical_url} target="_blank" rel="noreferrer">Open source</a>}
                          </div>
                          <b>{event.exposure_found ? `${money(event.aggregate_exposure_pct)}% exposure` : event.reason || "No matching holding"}</b>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <Empty>{eventData ? "No events found for this filter." : "Load collected events or collect from an approved feed."}</Empty>
                  )}
                </Panel>
              )}

              {assistantSubtab === "docs" && (
                <Panel title="PDF Factsheets & Disclosures">
                  <div className="upload-block">
                    <div className="field"><label>Upload a text-based PDF factsheet, SID or disclosure</label><input id="document-upload-input" type="file" accept="application/pdf,.pdf" onChange={(e) => setSelectedDocument(e.target.files?.[0] || null)} /></div>
                    <div className="field"><label>Document title</label><input value={documentTitle} onChange={(e) => setDocumentTitle(e.target.value)} placeholder="Optional title" /></div>
                    <button className="secondary" disabled={busy || !selectedDocument} onClick={importDocument}>Upload and index PDF</button>
                    {selectedDocument && <p className="upload-selected">Selected: {selectedDocument.name}</p>}
                  </div>
                  <div className="toolbar">
                    <input value={documentQuery} onChange={(e) => setDocumentQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && runDocuments()} />
                    <button className="primary" disabled={busy} onClick={runDocuments}>Search documents</button>
                  </div>
                  {data?.document_id ? (
                    <p className="muted">Uploaded {data.title} · Document #{data.document_id} · {data.page_count} page(s)</p>
                  ) : data?.results?.length ? (
                    data.results.map((item, i) => (
                      <article className="document-result" key={i}>
                        <div><strong>{item.title}</strong><small>Page {item.page_number || "—"}</small></div>
                        <p>{item.text}</p>
                      </article>
                    ))
                  ) : (
                    <Empty>{data ? "No matching document chunks." : "Search indexed PDFs and factsheets."}</Empty>
                  )}
                </Panel>
              )}
            </>
          )}

          {busy && (
            <div className="loading">
              <span></span> {busyStep || "Working…"} ({elapsedSec}s)
            </div>
          )}
          {error && <div className="error">{error}</div>}
        </div>
        <footer>Personal workspace · Metrics are deterministic · AI summaries are evidence-bounded</footer>
      </main>

      {modalSecurity && (
        <SecurityModal
          securityKey={modalSecurity.key}
          securityName={modalSecurity.name}
          schemeCodes={schemeCodes}
          dateTo={dateTo}
          onClose={closeSecurityModal}
        />
      )}
    </div>
  );
}
