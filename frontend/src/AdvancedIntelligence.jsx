import { useState } from "react";
import { request } from "./api";

const pretty = (value) => JSON.stringify(value, null, 2);
const number = (value) => value == null ? "—" : Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 });

function Panel({ title, children }) {
  return <section className="panel"><div className="panel-head"><h2>{title}</h2></div>{children}</section>;
}

export default function AdvancedIntelligence({ tab, schemeCodes, dateFrom, dateTo }) {
  const [securityKey, setSecurityKey] = useState("");
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function load() {
    setBusy(true);
    setError("");
    setData(null);
    try {
      if (!schemeCodes?.length) throw new Error("Enter at least one valid scheme code in the workspace.");
      const params = new URLSearchParams();
      if (dateTo) params.set("as_of", dateTo);
      let path;
      if (tab === "Fund Profile") {
        if (dateFrom) params.set("start_date", dateFrom);
        path = `/fund-intelligence/schemes/${schemeCodes[0]}/profile?${params}`;
      } else if (tab === "Actual Exposure") {
        schemeCodes.forEach((code) => params.append("scheme_codes", String(code)));
        path = `/fund-intelligence/portfolio/actual-exposure?${params}`;
      } else {
        if (!securityKey.trim()) throw new Error("Enter a normalized security key, ISIN or symbol key.");
        schemeCodes.forEach((code) => params.append("scheme_codes", String(code)));
        path = `/market-data/securities/${encodeURIComponent(securityKey.trim())}?${params}`;
      }
      setData(await request(path));
    } catch (exception) {
      setError(exception.message);
    } finally {
      setBusy(false);
    }
  }

  return <div className="advanced-intelligence">
    <Panel title={tab}>
      <p className="muted">
        {tab === "Fund Profile" && "A consolidated view of performance, category position, benchmark mapping, disclosures and stored events."}
        {tab === "Actual Exposure" && "Investor-ledger-weighted equity and sector exposure across the selected funds."}
        {tab === "Security Intelligence" && "Source-attributed market observations, dated fundamentals, corporate events and AMC-disclosed fund positions."}
      </p>
      {tab === "Security Intelligence" && <div className="field"><label>Security key / ISIN / mapped symbol key</label><input value={securityKey} onChange={(event) => setSecurityKey(event.target.value)} placeholder="e.g. INE002A01018 or RELIANCE.NSE" /></div>}
      <div className="muted">Selected schemes: {schemeCodes.join(", ") || "none"} · As of: {dateTo || "latest available"}</div>
      <button className="primary" disabled={busy} onClick={load}>{busy ? "Loading…" : "Load intelligence"}</button>
      {error && <div className="error">{error}</div>}
    </Panel>
    {data && <Panel title="Structured results">
      {tab === "Fund Profile" && <div className="analysis-grid">{Object.entries(data.sections || {}).map(([key, section]) => <div className="metric" key={key}><small>{key.replaceAll("_", " ")}</small><strong>{section.status || "unknown"}</strong></div>)}</div>}
      {tab === "Actual Exposure" && <><div className="analysis-grid"><div className="metric"><small>Portfolio value</small><strong>₹{number(data.total_value_inr)}</strong></div><div className="metric"><small>Covered funds</small><strong>{number(data.covered_fund_count)}</strong></div><div className="metric"><small>Equity securities</small><strong>{number(data.security_count)}</strong></div></div>{data.warning && <p className="muted">{data.warning}</p>}</>}
      {tab === "Security Intelligence" && <><div className="analysis-grid"><div className="metric"><small>Last price</small><strong>{data.market?.last_price == null ? "—" : `₹${number(data.market.last_price)}`}</strong></div><div className="metric"><small>Quote freshness</small><strong>{data.market?.freshness || "unavailable"}</strong></div><div className="metric"><small>Fundamentals</small><strong>{data.fundamentals?.availability || "unavailable"}</strong></div><div className="metric"><small>Fund positions</small><strong>{number(data.portfolio_coverage?.matched_scheme_count)}</strong></div></div>{data.limitations?.map((item) => <p className="muted" key={item}>{item}</p>)}</>}
      <details><summary>View full response and source metadata</summary><pre className="json-evidence">{pretty(data)}</pre></details>
    </Panel>}
  </div>;
}
