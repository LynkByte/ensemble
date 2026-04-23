/* ensemble-mcp — Bug Report page (Bug Hunter agent) */

const SEV_COLOR = {
  Critical: { bg: "var(--danger-bg)", fg: "var(--danger)" },
  High:     { bg: "var(--warning-bg)", fg: "var(--warning)" },
  Medium:   { bg: "var(--info-bg)", fg: "var(--info)" },
  Low:      { bg: "var(--bg-sunken)", fg: "var(--ink-3)" },
  Info:     { bg: "var(--bg-sunken)", fg: "var(--ink-4)" },
};

const BugReportPage = () => {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("bugs");
  const [sevFilter, setSevFilter] = useState("all");
  const [selected, setSelected] = useState(null);

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

  // Derive bug list and call usePagination BEFORE any conditional return
  // (React Rules of Hooks: hooks must always be called in the same order)
  const bugs = (report && report.bugs) || [];
  const filtered = bugs.filter(b => sevFilter === "all" || b.severity === sevFilter);
  const pg = usePagination(filtered, 8, sevFilter);

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

  const hasGeneratedReport =
    Boolean(report.markdown || report.generated_at || report.trend?.history?.length);
  if (!hasGeneratedReport) {
    return (
      <>
        <div className="page-head">
          <div>
            <h1 className="page-title">Bug Report</h1>
            <p className="page-desc">Reports directory is configured, but no Bug Hunter report has been generated yet.</p>
          </div>
        </div>
        <div className="card" style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>
          <Icon name="bug-report" size={32} />
          <p style={{ marginTop: 12 }}>Run the Bug Hunter agent to generate a report.</p>
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
  const smells = r.smells || [];
  const healthBreakdown = r.health_breakdown || [];
  const structure = r.structure || {};
  const structIssues = structure.issues || [];
  const structSuggestions = structure.suggestions || [];
  const arch = r.architecture || null;
  const refactorPlan = r.refactor_plan || [];
  const tests = r.tests || null;
  const ci = r.ci || null;

  const healthColor = healthScore >= 85 ? "var(--success)"
                    : healthScore >= 60 ? "var(--warning)"
                    : "var(--danger)";

  const severityLevels = ["Critical", "High", "Medium", "Low", "Info"];
  const bugsByS = Object.fromEntries(severityLevels.map(s => [s, 0]));
  bugs.forEach(b => { if (bugsByS[b.severity] !== undefined) bugsByS[b.severity]++; });

  const hasTrend = history.length >= 2;
  const hasBreakdown = healthBreakdown.length > 0;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Bug Report</h1>
          <p className="page-desc">
            Latest Bug Hunter scan
            {r.project && <> · <span className="tag">{r.project}</span></>}
            {(r.branch || r.commit) && <> · <span className="tag">{[r.branch, r.commit].filter(Boolean).join("@")}</span></>}
            {r.generated_at && <> · {r.generated_at}</>}
            {r.duration_sec != null && <> · {r.duration_sec}s</>}
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost"><Icon name="download" size={14}/> Markdown</button>
          <button className="btn btn-secondary"><Icon name="external" size={14}/> History</button>
          <button className="btn btn-primary"><Icon name="refresh" size={14}/> Re-scan</button>
        </div>
      </div>

      {/* Hero: health gauge + severity breakdown + CI */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: ci ? "240px 1fr 1fr" : "240px 1fr", gap: 0 }}>
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

          {/* Bug severity breakdown */}
          <div style={{ padding: 20, borderRight: ci ? "1px solid var(--border)" : "none" }}>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--ink-3)", fontWeight: 600, marginBottom: 12 }}>
              Bugs by severity · {totalBugs} total
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {severityLevels.map(s => {
                const pct = totalBugs > 0 ? Math.round((bugsByS[s]/totalBugs)*100) : 0;
                const c = SEV_COLOR[s];
                return (
                  <div key={s} style={{ background: c.bg, padding: "10px 12px", borderRadius: 6 }}>
                    <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", color: c.fg, fontWeight: 600 }}>{s}</div>
                    <div style={{ fontSize: 22, fontWeight: 600, color: c.fg, fontFamily: "var(--font-mono)", lineHeight: 1.1, marginTop: 2 }}>{bugsByS[s]}</div>
                    <div style={{ fontSize: 11, color: c.fg, opacity: 0.7, fontFamily: "var(--font-mono)" }}>{pct}%</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* CI Quality Gate */}
          {ci && (
            <div style={{ padding: 20 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
                <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--ink-3)", fontWeight: 600 }}>CI Quality Gate</div>
                <span className={`badge ${ci.status === "PASS" ? "badge-success" : "badge-danger"}`} style={{ fontSize: 11 }}>
                  {ci.status === "PASS" ? <><Icon name="check" size={10}/> PASS</> : "FAIL"}
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {(ci.checks || []).map(c => (
                  <div key={c.name} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                    <span style={{
                      width: 14, height: 14, borderRadius: "50%",
                      background: c.ok ? "var(--success-bg)" : "var(--warning-bg)",
                      color: c.ok ? "var(--success)" : "var(--warning)",
                      display: "grid", placeItems: "center", flexShrink: 0
                    }}>
                      <Icon name={c.ok ? "check" : "x-small"} size={9} />
                    </span>
                    <span style={{ color: "var(--ink-2)", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.name}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--ink-3)" }}>{c.value}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Trend + Health breakdown row */}
      {(hasTrend || hasBreakdown) && (
        <div style={{ display: "grid", gridTemplateColumns: hasTrend && hasBreakdown ? "1fr 1fr" : "1fr", gap: 16, marginBottom: 16 }}>
          {hasTrend && (
            <div className="card">
              <div className="card-head">
                <h3 className="card-title">Historical trend · {history.length} runs</h3>
                <span className="card-sub">{direction}</span>
              </div>
              <div className="card-body" style={{ padding: 16 }}>
                <TrendChart history={history} />
              </div>
            </div>
          )}

          {hasBreakdown && (
            <div className="card">
              <div className="card-head">
                <h3 className="card-title">Health breakdown · {healthScore}/100</h3>
                <span className="card-sub">{healthBreakdown.length} pillars</span>
              </div>
              <div className="card-body" style={{ padding: "12px 16px" }}>
                {healthBreakdown.map(p => {
                  const pct = p.max > 0 ? (p.score/p.max)*100 : 0;
                  const c = pct >= 85 ? "var(--success)" : pct >= 60 ? "var(--warning)" : "var(--danger)";
                  return (
                    <div key={p.pillar} style={{ padding: "8px 0", borderBottom: "1px dashed var(--border)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                        <span style={{ fontSize: 12.5, fontWeight: 500 }}>{p.pillar}</span>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--ink-3)" }}>{p.score}<span style={{ color: "var(--ink-4)" }}>/{p.max}</span></span>
                      </div>
                      <div style={{ height: 4, background: "var(--bg-sunken)", borderRadius: 2, overflow: "hidden", marginBottom: 4 }}>
                        <div style={{ height: "100%", width: `${pct}%`, background: c }} />
                      </div>
                      {p.note && <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{p.note}</div>}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tabs */}
      <div className="toolbar">
        {[
          ["bugs",        `Bugs${totalBugs ? ` · ${totalBugs}` : ""}`],
          ["smells",      `Code smells${codeSmells ? ` · ${codeSmells}` : ""}`],
          ["structure",   "Structure"],
          ["architecture","Architecture"],
          ["refactor",    `Refactor plan${refactorPlan.length ? ` · ${refactorPlan.length}` : ""}`],
          ["tests",       tests ? `Tests · ${tests.passed || 0}/${(tests.passed || 0)+(tests.failed || 0)}` : "Tests"],
        ].map(([k, l]) => (
          <button key={k} className={`filter-chip ${tab===k?"active":""}`} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>

      {/* Bugs tab */}
      {tab === "bugs" && (
        <>
          <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
            {["all", ...severityLevels].map(s => (
              <button key={s} className={`filter-chip ${sevFilter===s?"active":""}`} onClick={() => setSevFilter(s)}>{s}</button>
            ))}
          </div>
          {filtered.length === 0 ? (
            <div className="card" style={{ padding: 32, textAlign: "center", color: "var(--ink-3)" }}>No bugs found.</div>
          ) : (
            <div className="card">
              <table className="table">
                <thead>
                  <tr>
                    <th>ID</th><th>Title</th><th>Severity</th>
                    <th style={{ textAlign: "right" }}>CVSS</th>
                    <th>Category</th><th>Location</th>
                  </tr>
                </thead>
                <tbody>
                  {pg.slice.map(b => {
                    const c = SEV_COLOR[b.severity] || SEV_COLOR.Info;
                    return (
                      <tr key={b.id} onClick={() => setSelected(b)} style={{ cursor: "pointer" }}>
                        <td className="mono">{b.id}</td>
                        <td style={{ fontWeight: 500 }}>{b.title}</td>
                        <td>
                          <span className="badge" style={{ background: c.bg, color: c.fg, borderColor: "transparent" }}>{b.severity}</span>
                        </td>
                        <td className="mono" style={{ textAlign: "right" }}>
                          <span style={{ color: c.fg, fontWeight: 500 }}>{(b.cvss || 0).toFixed(1)}</span>
                        </td>
                        <td><span className="badge">{b.category}</span></td>
                        <td className="mono dim">{b.location}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <Pagination {...pg} label="bugs" pageSizes={[8, 25, 50]} />
            </div>
          )}
        </>
      )}

      {/* Code Smells tab */}
      {tab === "smells" && (
        smells.length === 0 ? (
          <div className="card" style={{ padding: 32, textAlign: "center", color: "var(--ink-3)" }}>No code smells data available.</div>
        ) : (
          <div className="card">
            <table className="table">
              <thead>
                <tr>
                  <th>Type</th><th style={{ textAlign: "right" }}>Count</th>
                  <th>Location</th><th>Suggested fix</th>
                </tr>
              </thead>
              <tbody>
                {smells.map((s, idx) => (
                  <tr key={`${s.type}-${idx}`}>
                    <td style={{ fontWeight: 500 }}>{s.type}</td>
                    <td className="mono" style={{ textAlign: "right" }}>{s.count}</td>
                    <td className="mono dim">{s.location}</td>
                    <td style={{ color: "var(--ink-2)" }}>{s.fix}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* Structure tab */}
      {tab === "structure" && (
        structIssues.length === 0 && structSuggestions.length === 0 ? (
          <div className="card" style={{ padding: 32, textAlign: "center", color: "var(--ink-3)" }}>No structure data available.</div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            <div className="card">
              <div className="card-head"><h3 className="card-title">Issues</h3></div>
              <div className="card-body">
                {structIssues.length === 0 ? (
                  <div style={{ padding: 12, color: "var(--ink-3)", fontSize: 12.5 }}>No issues found.</div>
                ) : structIssues.map((x, i) => (
                  <div key={i} style={{ padding: "8px 10px", background: "var(--warning-bg)", color: "var(--warning)", borderRadius: 4, fontSize: 12.5, marginBottom: 6 }}>{x}</div>
                ))}
              </div>
            </div>
            <div className="card">
              <div className="card-head"><h3 className="card-title">Suggestions</h3></div>
              <div className="card-body">
                {structSuggestions.length === 0 ? (
                  <div style={{ padding: 12, color: "var(--ink-3)", fontSize: 12.5 }}>No suggestions.</div>
                ) : structSuggestions.map((x, i) => (
                  <div key={i} style={{ padding: "8px 10px", background: "var(--success-bg)", color: "var(--success)", borderRadius: 4, fontSize: 12.5, marginBottom: 6 }}>{x}</div>
                ))}
              </div>
            </div>
          </div>
        )
      )}

      {/* Architecture tab */}
      {tab === "architecture" && (
        !arch ? (
          <div className="card" style={{ padding: 32, textAlign: "center", color: "var(--ink-3)" }}>No architecture data available.</div>
        ) : (
          <div className="card">
            <div className="card-body">
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 18 }}>
                <div style={{ padding: 14, background: "var(--bg-sunken)", borderRadius: 8 }}>
                  <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--ink-3)", fontWeight: 600, marginBottom: 6 }}>Detected</div>
                  <div style={{ fontSize: 15, fontWeight: 600 }}>{arch.detected || "Unknown"}</div>
                  {arch.score != null && <div style={{ marginTop: 6, fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--ink-3)" }}>fit score {arch.score}/100</div>}
                </div>
                <div style={{ padding: 14, background: "var(--accent-50)", borderRadius: 8 }}>
                  <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--accent-600)", fontWeight: 600, marginBottom: 6 }}>Recommended</div>
                  <div style={{ fontSize: 15, fontWeight: 600, color: "var(--accent-600)" }}>{arch.recommended || "—"}</div>
                </div>
              </div>
              {arch.rationale && <p style={{ fontSize: 13, lineHeight: 1.6, margin: "0 0 14px", color: "var(--ink-2)" }}>{arch.rationale}</p>}
              {(arch.violations || []).length > 0 && (
                <>
                  <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "0 0 8px" }}>Violations</h4>
                  {arch.violations.map((v, i) => (
                    <div key={i} style={{ padding: "8px 10px", background: "var(--danger-bg)", color: "var(--danger)", borderRadius: 4, fontFamily: "var(--font-mono)", fontSize: 12, marginBottom: 4 }}>{v}</div>
                  ))}
                </>
              )}
            </div>
          </div>
        )
      )}

      {/* Refactor Plan tab */}
      {tab === "refactor" && (
        refactorPlan.length === 0 ? (
          <div className="card" style={{ padding: 32, textAlign: "center", color: "var(--ink-3)" }}>No refactor plan available.</div>
        ) : (
          <div className="card">
            <div>
              {refactorPlan.map(s => (
                <div key={s.step} style={{ padding: "14px 18px", borderBottom: "1px solid var(--border)", display: "grid", gridTemplateColumns: "36px 1fr 80px 80px", gap: 12, alignItems: "center" }}>
                  <div style={{ width: 28, height: 28, borderRadius: "50%", background: "var(--bg-sunken)", display: "grid", placeItems: "center", fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600 }}>{s.step}</div>
                  <div>
                    <div style={{ fontSize: 13, fontWeight: 500, marginBottom: 2 }}>{s.title}</div>
                    <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{s.desc}</div>
                  </div>
                  <div><span className="badge">effort {s.effort}</span></div>
                  <div><span className="badge badge-accent">impact {s.impact}</span></div>
                </div>
              ))}
            </div>
          </div>
        )
      )}

      {/* Tests tab */}
      {tab === "tests" && (
        !tests ? (
          <div className="card" style={{ padding: 32, textAlign: "center", color: "var(--ink-3)" }}>No test data available.</div>
        ) : (
          <>
            <div className="stat-grid" style={{ gridTemplateColumns: `repeat(${[true, true, true, tests.coverage_line != null, tests.coverage_branch != null].filter(Boolean).length}, 1fr)` }}>
              <div className="stat"><div className="stat-label" style={{ color: "var(--success)" }}>Passed</div><div className="stat-value">{tests.passed || 0}</div></div>
              <div className="stat"><div className="stat-label" style={{ color: "var(--danger)" }}>Failed</div><div className="stat-value">{tests.failed || 0}</div></div>
              <div className="stat"><div className="stat-label">Skipped</div><div className="stat-value">{tests.skipped || 0}</div></div>
              {tests.coverage_line != null && (
                <div className="stat"><div className="stat-label">Line cov</div><div className="stat-value">{tests.coverage_line}<span className="stat-unit">%</span></div></div>
              )}
              {tests.coverage_branch != null && (
                <div className="stat"><div className="stat-label">Branch cov</div><div className="stat-value">{tests.coverage_branch}<span className="stat-unit">%</span></div></div>
              )}
            </div>
            {(tests.failures || []).length > 0 && (
              <div className="card">
                <div className="card-head"><h3 className="card-title">Failures</h3><span className="card-sub">{tests.duration_sec != null ? `${tests.duration_sec}s total` : ""}</span></div>
                <table className="table">
                  <thead><tr><th>Test</th><th>Kind</th><th>Location</th></tr></thead>
                  <tbody>
                    {tests.failures.map(f => (
                      <tr key={f.name}>
                        <td className="mono" style={{ fontWeight: 500 }}>{f.name}</td>
                        <td><span className={`badge ${f.kind==="security"?"badge-danger":f.kind==="flaky"?"badge-warning":"badge-info"}`}>{f.kind}</span></td>
                        <td className="mono dim">{f.file}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )
      )}

      {selected && (
        <Drawer title={`${selected.id} · ${selected.title}`} onClose={() => setSelected(null)} footer={
          <>
            <button className="btn btn-ghost" onClick={() => setSelected(null)}>Dismiss</button>
            <div style={{ flex: 1 }} />
            <button
              className="btn btn-secondary"
              disabled={!selected.fix}
              onClick={() => selected.fix && navigator.clipboard?.writeText(selected.fix)}
            >
              <Icon name="copy" size={13}/> Copy fix
            </button>
            <button className="btn btn-accent" disabled title="Open file action is not wired yet">
              <Icon name="external" size={13}/> Open file
            </button>
          </>
        }>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
            <span className="badge" style={{ background: (SEV_COLOR[selected.severity] || SEV_COLOR.Info).bg, color: (SEV_COLOR[selected.severity] || SEV_COLOR.Info).fg, borderColor: "transparent" }}>{selected.severity}</span>
            <span className="badge">CVSS {(selected.cvss || 0).toFixed(1)}</span>
            <span className="badge">{selected.category}</span>
          </div>

          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "0 0 6px" }}>Location</h4>
          <div style={{ padding: "8px 10px", background: "var(--bg-sunken)", borderRadius: 4, fontFamily: "var(--font-mono)", fontSize: 12 }}>{selected.location}</div>

          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>CVSS breakdown</h4>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
            {[["Impact", selected.impact, 4],["Exploit", selected.exploitability, 3],["Scope", selected.scope, 2],["Conf.", selected.confidence, 1]].map(([l, v, m]) => (
              <div key={l} style={{ padding: 10, background: "var(--bg-sunken)", borderRadius: 6 }}>
                <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", fontWeight: 600 }}>{l}</div>
                <div style={{ fontSize: 18, fontFamily: "var(--font-mono)", fontWeight: 600, marginTop: 2 }}>{v != null ? v : "—"}<span style={{ fontSize: 12, color: "var(--ink-4)" }}>/{m}</span></div>
              </div>
            ))}
          </div>

          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>Suggested fix</h4>
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, padding: "12px 14px", background: "var(--success-bg)", color: "var(--success)", borderRadius: 6 }}>{selected.fix || "No fix suggestion available."}</p>
        </Drawer>
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
  const scores = history.map(row => row.health || 0);
  const bugs = history.map(row => row.bugs || 0);
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
