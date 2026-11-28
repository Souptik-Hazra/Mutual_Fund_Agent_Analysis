import { useEffect, useState } from "react";
import { request } from "./api";

const pretty = (value) => JSON.stringify(value, null, 2);
const number = (value) =>
  value == null ? "—" : Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 });
const percent = (value) => (value == null ? "—" : `${(Number(value) * 100).toFixed(2)}%`);

function Panel({ title, children }) {
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{title}</h2>
      </div>
      {children}
    </section>
  );
}

export function FundProfileView({ data }) {
  const sections = data.sections || {};
  const perf = sections.performance_and_risk?.data;
  const cat = sections.category_position?.data;
  const port = sections.portfolio_disclosure?.data;
  const events = sections.market_events?.data;
  const bench = sections.benchmark_mapping?.benchmark;

  return (
    <>
      {data.scheme && (
        <div className="event-row">
          <div>
            <strong>{data.scheme.scheme_name}</strong>
            <small>
              Code {data.scheme.scheme_code} · {data.scheme.fund_house || "—"} ·{" "}
              {data.scheme.category || "—"} · {data.scheme.plan_type || "—"} ·{" "}
              {data.scheme.option_type || "—"}
            </small>
          </div>
          {bench && (
            <b>
              Benchmark: {bench.code} ({bench.source})
            </b>
          )}
        </div>
      )}

      <div className="analysis-grid">
        {Object.entries(sections).map(([key, section]) => (
          <div className="metric" key={key}>
            <small>{key.replaceAll("_", " ")}</small>
            <strong>{section.status || "unknown"}</strong>
          </div>
        ))}
      </div>

      {perf && (
        <div className="profile-section">
          <h3>Performance & Risk ({perf.start_date} to {perf.end_date})</h3>
          <div className="analysis-grid">
            <div className="metric"><small>CAGR</small><strong>{percent(perf.cagr)}</strong></div>
            <div className="metric"><small>Absolute return</small><strong>{percent(perf.absolute_return)}</strong></div>
            <div className="metric"><small>Annual volatility</small><strong>{percent(perf.risk?.annualized_volatility)}</strong></div>
            <div className="metric"><small>Max drawdown</small><strong>{percent(perf.drawdown?.maximum_drawdown)}</strong></div>
            <div className="metric"><small>Sharpe ratio</small><strong>{number(perf.risk?.sharpe_ratio)}</strong></div>
            <div className="metric"><small>Sortino ratio</small><strong>{number(perf.risk?.sortino_ratio)}</strong></div>
            <div className="metric"><small>Alpha (ann.)</small><strong>{percent(perf.benchmark?.annualized_alpha)}</strong></div>
            <div className="metric"><small>Beta</small><strong>{number(perf.benchmark?.beta)}</strong></div>
          </div>
        </div>
      )}

      {cat?.selected_fund && (
        <div className="profile-section">
          <h3>Category Position · {cat.category}</h3>
          <div className="analysis-grid">
            <div className="metric"><small>Peer count</small><strong>{cat.peer_count}</strong></div>
            <div className="metric"><small>CAGR rank</small><strong>{cat.selected_fund.cagr_rank ?? "—"} / {cat.peer_count}</strong></div>
            <div className="metric"><small>CAGR percentile</small><strong>{cat.selected_fund.cagr_percentile == null ? "—" : `${number(cat.selected_fund.cagr_percentile)}%`}</strong></div>
            <div className="metric"><small>Sharpe rank</small><strong>{cat.selected_fund.sharpe_ratio_rank ?? "—"} / {cat.peer_count}</strong></div>
          </div>
        </div>
      )}

      {port?.holdings?.length > 0 && (
        <div className="profile-section">
          <h3>Top Disclosed Holdings · effective {port.effective_date}</h3>
          <p className="muted">Weight coverage: {number(port.weight_coverage_pct)}% · HHI: {number(port.hhi_0_to_1)}</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Security</th><th>Asset class</th><th>Sector</th><th>Weight</th></tr>
              </thead>
              <tbody>
                {port.holdings.slice(0, 10).map((h, i) => (
                  <tr key={i}>
                    <td>{h.security_name}</td>
                    <td>{h.asset_class}</td>
                    <td>{h.sector || "—"}</td>
                    <td>{h.weight_pct == null ? "—" : `${h.weight_pct}%`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {events?.events?.length > 0 && (
        <div className="profile-section">
          <h3>Linked Market Events ({events.events.length})</h3>
          <div className="event-list">
            {events.events.slice(0, 10).map((ev) => (
              <article className="event-row" key={ev.event_id}>
                <div>
                  <strong>{ev.title}</strong>
                  <small>{ev.event_date || "—"} · {ev.status} · {ev.source_key || "—"}</small>
                </div>
                <b>{ev.exposure_found ? `${number(ev.aggregate_exposure_pct)}% exposure` : "—"}</b>
              </article>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

export function SecurityIntelligenceView({ data }) {
  const market = data.market || null;
  const fundamentals = data.fundamentals || {};
  const metrics = fundamentals.metrics || {};
  const units = fundamentals.metric_units || {};
  const positions = data.portfolio_positions || [];
  const corpEvents = data.corporate_events || [];

  return (
    <>
      {data.identity && (
        <div className="event-row">
          <div>
            <strong>{data.identity.security_name || data.security_key}</strong>
            <small>
              Key: {data.security_key}
              {data.identity.isin ? ` · ISIN: ${data.identity.isin}` : ""}
              {data.identity.symbol ? ` · ${data.identity.exchange || "EX"}:${data.identity.symbol}` : ""}
            </small>
          </div>
          <b>{data.availability === "available" ? "Market data available" : "No market quote"}</b>
        </div>
      )}

      <div className="analysis-grid">
        <div className="metric">
          <small>Last price</small>
          <strong>{market?.last_price == null ? "—" : `₹${number(market.last_price)}`}</strong>
        </div>
        <div className="metric">
          <small>Day change</small>
          <strong className={market?.change_pct > 0 ? "pos" : market?.change_pct < 0 ? "neg" : ""}>
            {market?.change_pct == null ? "—" : `${number(market.change_pct)}%`}
          </strong>
        </div>
        <div className="metric">
          <small>Quote freshness</small>
          <strong>{market?.freshness || "unavailable"}</strong>
        </div>
        <div className="metric">
          <small>Fund positions</small>
          <strong>{number(data.portfolio_coverage?.matched_scheme_count)}</strong>
        </div>
      </div>

      {market && (
        <p className="muted">
          Day range: {market.day_low != null ? `₹${number(market.day_low)}` : "—"} to{" "}
          {market.day_high != null ? `₹${number(market.day_high)}` : "—"} · Volume:{" "}
          {number(market.volume)} · Status: {market.market_status || "—"} · Age:{" "}
          {market.age_hours != null ? `${market.age_hours}h` : "—"} · Source: {market.source_key || "—"}
        </p>
      )}

      {Object.keys(metrics).length > 0 && (
        <div className="profile-section">
          <h3>
            Dated Fundamentals (as of {fundamentals.as_of || "unknown"} · {fundamentals.freshness || "—"})
          </h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Metric</th><th>Value</th><th>Unit</th></tr>
              </thead>
              <tbody>
                {Object.entries(metrics).map(([k, v]) => (
                  <tr key={k}>
                    <td>{k.replaceAll("_", " ")}</td>
                    <td>{v == null ? "—" : number(v)}</td>
                    <td>{units[k] || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {positions.length > 0 && (
        <div className="profile-section">
          <h3>AMC-Disclosed Fund Positions ({positions.length})</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Scheme code</th><th>Effective date</th><th>Sector</th><th>Weight</th><th>Market value</th></tr>
              </thead>
              <tbody>
                {positions.map((pos, idx) => (
                  <tr key={`${pos.scheme_code}-${idx}`}>
                    <td>{pos.scheme_code}</td>
                    <td>{pos.effective_date}</td>
                    <td>{pos.sector || "—"}</td>
                    <td>{pos.weight_pct == null ? "—" : `${number(pos.weight_pct)}%`}</td>
                    <td>{pos.market_value == null ? "—" : `₹${number(pos.market_value)}`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {corpEvents.length > 0 && (
        <div className="profile-section">
          <h3>Corporate Events ({corpEvents.length})</h3>
          <div className="event-list">
            {corpEvents.map((ev, idx) => (
              <article className="event-row" key={idx}>
                <div>
                  <strong>{ev.title}</strong>
                  <small>{ev.event_date || "—"} · {ev.event_type || "other"} · {ev.verification_status || "unverified"}</small>
                </div>
                {ev.canonical_url && (
                  <a href={ev.canonical_url} target="_blank" rel="noreferrer">Source</a>
                )}
              </article>
            ))}
          </div>
        </div>
      )}

      {data.limitations?.map((item) => (
        <p className="muted" key={item}>{item}</p>
      ))}
    </>
  );
}

export function ActualExposureView({ data, dateTo, onSelectSecurity }) {
  return (
    <>
      <div className="analysis-grid">
        <div className="metric">
          <small>Portfolio value · {data.as_of_date || dateTo}</small>
          <strong>₹{number(data.total_valued_portfolio_inr)}</strong>
        </div>
        <div className="metric">
          <small>Valued funds</small>
          <strong>
            {number(data.coverage?.valued_fund_count)} / {number(data.coverage?.selected_fund_count)}
          </strong>
        </div>
        <div className="metric">
          <small>Holdings look-through</small>
          <strong>{number(data.coverage?.lookthrough_coverage_pct)}%</strong>
        </div>
        <div className="metric">
          <small>Equity securities</small>
          <strong>{number(data.equity_exposure?.length)}</strong>
        </div>
      </div>
      {data.warning && <p className="muted">{data.warning}</p>}
      {data.valued_funds?.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Fund</th><th>Units</th><th>NAV</th><th>NAV date</th><th>NAV age</th><th>Value (INR)</th>
              </tr>
            </thead>
            <tbody>
              {data.valued_funds.map((fund) => (
                <tr key={fund.scheme_code}>
                  <td>{fund.scheme_name}<small>{fund.scheme_code}</small></td>
                  <td>{number(fund.units)}</td>
                  <td>{number(fund.latest_nav)}</td>
                  <td>{fund.nav_date}</td>
                  <td>{fund.valuation_age_days} days</td>
                  <td>₹{number(fund.market_value_inr)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {[
        ...(data.excluded_funds || []).map((item) => item.reason),
        ...(data.disclosure_warnings || []).map((item) => item.reason),
        ...(data.data_quality_warnings || []).map((item) => item.reason),
      ].map((warning, index) => (
        <p className="muted" key={index}>{warning}</p>
      ))}
      {data.equity_exposure?.length > 0 && (
        <div className="profile-section">
          <h3>Underlying Equity Exposure (click any row to inspect security)</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Underlying share</th><th>Funds</th><th>Exposure (INR)</th><th>Portfolio weight</th></tr>
              </thead>
              <tbody>
                {data.equity_exposure.slice(0, 20).map((item) => (
                  <tr
                    key={item.security_key}
                    className={onSelectSecurity ? "clickable-row" : ""}
                    onClick={() => onSelectSecurity?.(item.security_key, item.security_name)}
                  >
                    <td>
                      {item.security_name}
                      <small>{item.security_key}</small>
                    </td>
                    <td>{item.funds_present}</td>
                    <td>₹{number(item.actual_exposure_inr)}</td>
                    <td>{number(item.actual_portfolio_weight_pct)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {data.sector_exposure?.length > 0 && (
        <div className="profile-section">
          <h3>Sector Exposure</h3>
          <div className="allocation-list">
            {data.sector_exposure.slice(0, 12).map((sector) => (
              <div className="allocation-row" key={sector.sector || "unknown"}>
                <span>{sector.sector || "Unclassified"}</span>
                <div className="allocation-track">
                  <i style={{ width: `${Math.max(0, Math.min(100, Number(sector.actual_portfolio_weight_pct || 0)))}%` }} />
                </div>
                <b>{number(sector.actual_portfolio_weight_pct)}%</b>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

export function SecurityModal({ securityKey, securityName, schemeCodes, dateTo, onClose }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!securityKey) return;
    let active = true;
    setBusy(true);
    setError("");
    const params = new URLSearchParams();
    if (dateTo) params.set("as_of", dateTo);
    (schemeCodes || []).forEach((code) => params.append("scheme_codes", String(code)));
    request(`/market-data/securities/${encodeURIComponent(securityKey)}?${params}`)
      .then((res) => active && setData(res))
      .catch((err) => active && setError(err.message))
      .finally(() => active && setBusy(false));
    return () => {
      active = false;
    };
  }, [securityKey, schemeCodes, dateTo]);

  if (!securityKey) return null;
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>{securityName || securityKey}</h2>
          <button className="secondary" onClick={onClose}>Close</button>
        </div>
        {busy && <div className="loading"><span></span> Loading security intelligence…</div>}
        {error && <div className="error">{error}</div>}
        {data && <SecurityIntelligenceView data={data} />}
      </div>
    </div>
  );
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
      if (!schemeCodes?.length && tab !== "Security Intelligence") {
        throw new Error("Enter at least one valid scheme code in the workspace.");
      }
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
        (schemeCodes || []).forEach((code) => params.append("scheme_codes", String(code)));
        path = `/market-data/securities/${encodeURIComponent(securityKey.trim())}?${params}`;
      }
      setData(await request(path));
    } catch (exception) {
      setError(exception.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="advanced-intelligence">
      <Panel title={tab}>
        {tab === "Security Intelligence" && (
          <div className="field">
            <label>Security key / ISIN / mapped symbol key</label>
            <input value={securityKey} onChange={(e) => setSecurityKey(e.target.value)} />
          </div>
        )}
        <button className="primary" disabled={busy} onClick={load}>
          {busy ? "Loading…" : "Load intelligence"}
        </button>
        {error && <div className="error">{error}</div>}
      </Panel>
      {data && (
        <Panel title="Structured results">
          {tab === "Fund Profile" && <FundProfileView data={data} />}
          {tab === "Actual Exposure" && <ActualExposureView data={data} dateTo={dateTo} />}
          {tab === "Security Intelligence" && <SecurityIntelligenceView data={data} />}
          <details>
            <summary>View raw JSON response</summary>
            <pre className="json-evidence">{pretty(data)}</pre>
          </details>
        </Panel>
      )}
    </div>
  );
}
