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
      if (dateTo) {
        params.set(
          tab === "Fund Profile" ? "end_date" : tab === "Actual Exposure" ? "as_of_date" : "as_of",
          dateTo,
        );
      }
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
      {tab === "Security Intelligence" && <div className="field"><label>Security key / ISIN / mapped symbol key</label><input value={securityKey} onChange={(event) => setSecurityKey(event.target.value)} placeholder="Enter the exact security_key from a holdings disclosure" /></div>}
      <div className="muted">Selected schemes: {schemeCodes.join(", ") || "none"} · {tab === "Actual Exposure" ? `Valuation as of: ${dateTo || "today"}` : `As of: ${dateTo || "latest available"}`}</div>
      <button className="primary" disabled={busy} onClick={load}>{busy ? "Loading…" : "Load intelligence"}</button>
      {error && <div className="error">{error}</div>}
    </Panel>
    {data && <Panel title="Structured results">
      {tab === "Fund Profile" && <div className="analysis-grid">{Object.entries(data.sections || {}).map(([key, section]) => <div className="metric" key={key}><small>{key.replaceAll("_", " ")}</small><strong>{section.status || "unknown"}</strong></div>)}</div>}
      {tab === "Actual Exposure" && <><div className="analysis-grid"><div className="metric"><small>Portfolio value · {data.as_of_date || dateTo}</small><strong>₹{number(data.total_valued_portfolio_inr)}</strong></div><div className="metric"><small>Valued funds</small><strong>{number(data.coverage?.valued_fund_count)} / {number(data.coverage?.selected_fund_count)}</strong></div><div className="metric"><small>Holdings look-through</small><strong>{number(data.coverage?.lookthrough_coverage_pct)}%</strong></div><div className="metric"><small>Equity securities</small><strong>{number(data.equity_exposure?.length)}</strong></div></div>{data.warning && <p className="muted">{data.warning}</p>}
        {data.valued_funds?.length > 0 && <div className="table-wrap"><table><thead><tr><th>Fund</th><th>Units</th><th>NAV</th><th>NAV date</th><th>NAV age</th><th>Value (INR)</th></tr></thead><tbody>{data.valued_funds.map((fund) => <tr key={fund.scheme_code}><td>{fund.scheme_name}<small>{fund.scheme_code}</small></td><td>{number(fund.units)}</td><td>{number(fund.latest_nav)}</td><td>{fund.nav_date}</td><td>{fund.valuation_age_days} days</td><td>₹{number(fund.market_value_inr)}</td></tr>)}</tbody></table></div>}
        {[...(data.excluded_funds || []).map((item) => item.reason), ...(data.disclosure_warnings || []).map((item) => item.reason), ...(data.data_quality_warnings || []).map((item) => item.reason)].map((warning, index) => <p className="muted" key={index}>{warning}</p>)}}
        {data.equity_exposure?.length > 0 && <div className="table-wrap"><table><thead><tr><th>Underlying share</th><th>Funds</th><th>Exposure (INR)</th><th>Portfolio weight</th></tr></thead><tbody>{data.equity_exposure.slice(0, 20).map((item) => <tr key={item.security_key}><td>{item.security_name}<small>{item.security_key}</small></td><td>{item.funds_present}</td><td>₹{number(item.actual_exposure_inr)}</td><td>{number(item.actual_portfolio_weight_pct)}%</td></tr>)}</tbody></table></div>}
        {data.sector_exposure?.length > 0 && <details><summary>Sector exposure</summary><pre className="json-evidence">{pretty(data.sector_exposure)}</pre></details>}</>}
      {tab === "Security Intelligence" && <><div className="analysis-grid"><div className="metric"><small>Last price</small><strong>{data.market?.last_price == null ? "—" : `₹${number(data.market.last_price)}`}</strong></div><div className="metric"><small>Quote freshness</small><strong>{data.market?.freshness || "unavailable"}</strong></div><div className="metric"><small>Fundamentals</small><strong>{data.fundamentals?.availability || "unavailable"}</strong></div><div className="metric"><small>Fund positions</small><strong>{number(data.portfolio_coverage?.matched_scheme_count)}</strong></div></div>{data.limitations?.map((item) => <p className="muted" key={item}>{item}</p>)}</>}
      <details><summary>View full response and source metadata</summary><pre className="json-evidence">{pretty(data)}</pre></details>
    </Panel>}
  </div>;
}
