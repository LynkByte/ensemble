/* ensemble-mcp — Bug Report page (Bug Hunter agent) */

const SEV_COLOR = {
  Critical: { bg: "var(--danger-bg)", fg: "var(--danger)" },
  High:     { bg: "var(--warning-bg)", fg: "var(--warning)" },
  Medium:   { bg: "var(--info-bg)", fg: "var(--info)" },
  Low:      { bg: "var(--bg-sunken)", fg: "var(--ink-3)" },
};

const BugReportPage = () => {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sevFilter, setSevFilter] = useState("all");
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState("bugs");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await API.reportsFull();
        if (cancelled) return;
        setReport(data);
      } catch (e) { if (!cancelled) setError(e.message); }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) return <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>Loading bug report…</div>;
  if (error) return <div style={{ padding: 40, textAlign: "center", color: "var(--danger)" }}>Error: {error}</div>;
  if (!report || !report.available) {
    return (
      <>
        <div className="page-head">
          <div>
            <h1 className="page-title">Bug Report</h1>
            <p className="page-desc">Bug Hunter agent reports are not available.</p>
          </div>
        </div>
        <div className="card" style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>
          <Icon name="bug-report" size={32} />
          <p style={{ marginTop: 12 }}>No bug reports found. Run the Bug Hunter agent to generate a report.</p>
          <p style={{ fontSize: 12, color: "var(--ink-4)" }}>{report?.message || "Reports directory not configured"}</p>
        </div>
      </>
    );
  }

  const r = report;
  const healthScore = r.summary?.health_score || 0;
  const totalBugs = r.summary?.total_bugs || 0;
  const codeSmells = r.summary?.code_smells || 0;
  const rating = r.summary?.rating || "Unknown";
  const trendData = r.trend || {};
  const history = trendData.history || [];
  const change = trendData.change || 0;
  const direction = trendData.direction || "stable";

  const healthColor = healthScore >= 85 ? "var(--success)"
                    : healthScore >= 60 ? "var(--warning)"
                    : "var(--danger)";

  // Since the full API doesn't return individual bugs/smells/structure/architecture/refactor/tests,
  // we show what's available from the summary + trend data

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Bug Report</h1>
          <p className="page-desc">
            Latest Bug Hunter scan · {r.generated_at || "—"}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost"><Icon name="download" size={14}/> Markdown</button>
          <button className="btn btn-secondary"><Icon name="external" size={14}/> History</button>
          <button className="btn btn-primary"><Icon name="refresh" size={14}/> Re-scan</button>
        </div>
      </div>

      {/* Hero: health gauge + summary */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 0 }}>
          {/* Gauge */}
          <div style={{ padding: 20, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
            <GaugeRing value={healthScore} color={healthColor} />
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--ink-3)", fontWeight: 600 }}>Code Health</div>
            <div style={{ fontSize: 13, color: healthColor, fontWeight: 600 }}>{rating}</div>
            {change !== 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, fontFamily: "var(--font-mono)", color: change > 0 ? "var(--success)" : "var(--danger)" }}>
                <Icon name={change > 0 ? "arrow-up" : "arrow-down"} size={11}/> {change > 0 ? "+" : ""}{change} vs. last scan
              </div>
            )}
          </div>

          {/* Summary stats */}
          <div style={{ padding: 20 }}>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--ink-3)", fontWeight: 600, marginBottom: 12 }}>
              Summary
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
              <div>
                <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", fontWeight: 600 }}>Total bugs</div>
                <div style={{ fontSize: 22, fontWeight: 600, fontFamily: "var(--font-mono)", lineHeight: 1.1, marginTop: 2 }}>{totalBugs}</div>
              </div>
              <div>
                <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", fontWeight: 600 }}>Code smells</div>
                <div style={{ fontSize: 22, fontWeight: 600, fontFamily: "var(--font-mono)", lineHeight: 1.1, marginTop: 2 }}>{codeSmells}</div>
              </div>
              <div>
                <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", fontWeight: 600 }}>Trend</div>
                <div style={{ fontSize: 16, fontWeight: 600, fontFamily: "var(--font-mono)", lineHeight: 1.1, marginTop: 2, color: direction === "improving" ? "var(--success)" : direction === "declining" ? "var(--danger)" : "var(--ink-2)" }}>
                  {direction}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Trend chart if history available */}
      {history.length >= 2 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div className="card-head">
            <h3 className="card-title">Historical trend · {history.length} runs</h3>
            <span className="card-sub">{direction}</span>
          </div>
          <div className="card-body" style={{ padding: 16 }}>
            <TrendChart history={history} />
          </div>
        </div>
      )}

      {/* Markdown content if available */}
      {r.markdown && (
        <div className="card">
          <div className="card-head">
            <h3 className="card-title">Full report</h3>
          </div>
          <div className="card-body" style={{ padding: 16 }}>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 12.5, fontFamily: "var(--font-mono)", lineHeight: 1.6, margin: 0, maxHeight: 600, overflow: "auto" }}>{r.markdown}</pre>
          </div>
        </div>
      )}
    </>
  );
};

/* ---- Gauge ring ---- */
const GaugeRing = ({ value, color, size = 140 }) => {
  const r = 56;
  const circ = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value || 0));
  const dash = (pct / 100) * circ;
  return (
    <div style={{ position: "relative", width: size, height: size }}>
      <svg width={size} height={size} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--bg-sunken)" strokeWidth="10" />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circ - dash}`} />
      </svg>
      <div style={{ position: "absolute", inset: 0, display: "grid", placeItems: "center", flexDirection: "column" }}>
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: 34, fontWeight: 600, letterSpacing: "-0.02em", fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>{value || 0}</div>
          <div style={{ fontSize: 11, color: "var(--ink-4)", fontFamily: "var(--font-mono)", marginTop: 2 }}>/ 100</div>
        </div>
      </div>
    </div>
  );
};

/* ---- Trend chart ---- */
const TrendChart = ({ history }) => {
  if (!history || history.length < 2) return null;
  const w = 480, h = 160, pad = 24;
  const xs = history.length;
  const scores = history.map(h => h.health || 0);
  const bugs = history.map(h => h.bugs || 0);
  const minY = 50, maxY = 100;
  const yScale = v => h - pad - ((v - minY) / (maxY - minY)) * (h - pad*2);
  const xScale = i => pad + (i / (xs - 1)) * (w - pad*2);
  const scorePath = scores.map((v, i) => `${i===0?"M":"L"}${xScale(i).toFixed(1)},${yScale(v).toFixed(1)}`).join(" ");

  const bugsMax = Math.max(...bugs, 1);
  const bugsMin = Math.min(...bugs);
  const bugsRange = bugsMax - bugsMin || 1;
  const bugsYScale = v => h - pad - ((v - bugsMin) / bugsRange) * (h - pad*2);
  const bugsPath = bugs.map((v, i) => `${i===0?"M":"L"}${xScale(i).toFixed(1)},${bugsYScale(v).toFixed(1)}`).join(" ");

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display: "block" }}>
        {[60, 70, 80, 90, 100].map(v => (
          <g key={v}>
            <line x1={pad} x2={w-pad} y1={yScale(v)} y2={yScale(v)} stroke="var(--border)" strokeDasharray="2 3" />
            <text x={4} y={yScale(v)+3} fontSize="10" fill="var(--ink-4)" fontFamily="var(--font-mono)">{v}</text>
          </g>
        ))}
        <path d={`${scorePath} L${xScale(xs-1)},${h-pad} L${xScale(0)},${h-pad} Z`} fill="var(--accent)" opacity="0.08" />
        <path d={scorePath} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        {scores.map((v, i) => (
          <circle key={i} cx={xScale(i)} cy={yScale(v)} r="3" fill="var(--accent-600)" stroke="var(--bg-elev)" strokeWidth="2" />
        ))}
        <path d={bugsPath} fill="none" stroke="var(--danger)" strokeWidth="1.5" strokeDasharray="4 3" opacity="0.7" />
        {bugs.map((v, i) => (
          <circle key={i} cx={xScale(i)} cy={bugsYScale(v)} r="2.5" fill="var(--danger)" />
        ))}
        {history.map((row, i) => (
          <text key={i} x={xScale(i)} y={h-6} fontSize="9.5" textAnchor="middle" fill="var(--ink-4)" fontFamily="var(--font-mono)">
            {(row.date || "").slice(5)}
          </text>
        ))}
      </svg>
      <div style={{ display: "flex", gap: 14, fontSize: 11, color: "var(--ink-3)", fontFamily: "var(--font-mono)", marginTop: 6 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><span style={{ width: 10, height: 2, background: "var(--accent)", display: "inline-block" }} /> health</span>
        <span style={{ display: "flex", alignItems: "center", gap: 5 }}><span style={{ width: 10, height: 2, background: "var(--danger)", display: "inline-block", borderTop: "1px dashed" }} /> bugs</span>
      </div>
    </div>
  );
};

Object.assign(window, { BugReportPage, SEV_COLOR, GaugeRing, TrendChart });
