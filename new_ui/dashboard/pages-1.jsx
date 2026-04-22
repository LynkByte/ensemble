/* ensemble-mcp — Summary, Patterns, Skills pages */

const SummaryPage = ({ onNavigate }) => {
  const s = MOCK.summary;
  const h = MOCK.health;
  const act = usePagination(MOCK.recentActivity, 20, "recent");
  const stats = [
    { label: "Patterns",   value: s.pattern_count,      delta: "+42 this week", up: true,  spark: s.pattern_growth_30d },
    { label: "Skills",     value: s.active_skills,      sub: `${s.pending_suggestions} pending`, spark: [3,5,4,6,8,7,9,11,14,17,19,21,23] },
    { label: "Projects",   value: s.project_count,      sub: "8 indexed · 1 stale",    spark: [2,3,4,4,5,5,6,7,7,8,8,8] },
    { label: "Drift / 30d",value: s.drift_checks_30d,   delta: "18% aligned ratio",    spark: [8,12,10,14,9,18,22,14,12,18,24,15,12,14,18,22,16,11,14,18,22,26,19,14,18,23,27,22,17,14] },
    { label: "Sessions",   value: s.session_count,      sub: `${s.sessions_running} running · ${s.sessions_completed} done`, spark: [2,3,3,4,5,5,6,7,8] },
    { label: "MCP calls today", value: s.calls_today.toLocaleString(), delta: "+287% vs. yesterday", up: true, spark: s.calls_7d },
  ];

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Summary</h1>
          <p className="page-desc">Aggregate state of the local ensemble-mcp server. All processing is local — SQLite + ONNX, zero cloud calls.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost"><Icon name="refresh" size={14} /> Refresh</button>
          <button className="btn btn-secondary"><Icon name="external" size={14} /> Open API docs</button>
        </div>
      </div>

      <div className="stat-grid">
        {stats.map(st => (
          <div key={st.label} className="stat">
            <div className="stat-label">{st.label}</div>
            <div className="stat-value">{st.value}</div>
            {st.delta && <div className={`stat-delta ${st.up ? "up" : ""}`}>{st.up && <Icon name="arrow-up" size={10}/>} {st.delta}</div>}
            {st.sub && <div className="stat-delta">{st.sub}</div>}
            <div className="stat-spark"><Sparkline data={st.spark} /></div>
          </div>
        ))}
      </div>

      <div className="summary-grid">
        <div className="card">
          <div className="card-head">
            <h3 className="card-title"><Icon name="zap" size={14} /> Recent MCP calls</h3>
            <span className="card-sub">{MOCK.recentActivity.length} logged · live</span>
          </div>
          <div>
            {act.slice.map((a, i) => (
              <div key={act.from + i} className="activity-row">
                <span className="tool">{a.tool}</span>
                <span className="proj">{a.project}{!a.ok && <span className="badge badge-danger" style={{marginLeft:8, fontSize:10}}>err</span>}</span>
                <span className="dur">{fmtDuration(a.duration_ms)}</span>
                <span className="time">{a.ts}</span>
              </div>
            ))}
          </div>
          <Pagination {...act} label="calls" pageSizes={[16, 20, 32]} />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <div className="card-head">
              <h3 className="card-title">Call volume · 24h</h3>
              <span className="card-sub">GMT</span>
            </div>
            <div className="card-body">
              <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 80, marginBottom: 6 }}>
                {s.calls_by_hour.map((v, i) => {
                  const max = Math.max(...s.calls_by_hour);
                  const h = Math.max(2, (v / max) * 72);
                  const isPeak = v === max;
                  return (
                    <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                      <div style={{
                        width: "100%", height: `${h}px`,
                        background: isPeak ? "var(--accent)" : "var(--border-strong)",
                        borderRadius: 2, transition: "background .15s"
                      }} />
                    </div>
                  );
                })}
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10.5, color: "var(--ink-4)", fontFamily: "var(--font-mono)" }}>
                <span>00</span><span>06</span><span>12</span><span>18</span><span>24</span>
              </div>
            </div>
          </div>

          <BugHunterCard onOpen={() => onNavigate && onNavigate("bug-report")} />

          <div className="card">
            <div className="card-head"><h3 className="card-title"><Icon name="database" size={14} /> Server health</h3></div>
            <div className="card-body">
              <dl style={{ margin: 0 }}>
                <div className="key-value"><dt>status</dt><dd><span className="badge badge-success"><Icon name="check" size={10}/> ok</span></dd></div>
                <div className="key-value"><dt>version</dt><dd>{h.version}</dd></div>
                <div className="key-value"><dt>uptime</dt><dd>{fmtUptime(h.uptime_seconds)}</dd></div>
                <div className="key-value"><dt>db_size</dt><dd>{fmtBytes(h.db_size_bytes)}</dd></div>
                <div className="key-value"><dt>embedding</dt><dd>{h.embedding_model} · {h.embedding_dims}d · {h.avg_embedding_ms}ms</dd></div>
                <div className="key-value"><dt>bind</dt><dd>127.0.0.1:8787</dd></div>
              </dl>
            </div>
          </div>
        </div>
      </div>
    </>
  );
};

/* ---- Patterns page ---- */
const PatternsPage = () => {
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState(null);

  const cats = ["all", "problem-solution", "how-it-works", "gotcha", "decision", "trade-off", "what-changed", "discovery"];
  const filtered = useMemo(() => {
    return MOCK.patterns.filter(p =>
      (filter === "all" || p.category === filter) &&
      (!q || p.name.includes(q) || p.context.toLowerCase().includes(q.toLowerCase()))
    );
  }, [filter, q]);
  const pg = usePagination(filtered, 10, `${filter}|${q}`);
  const rows = pg.slice;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Patterns</h1>
          <p className="page-desc">Semantic memory of past solutions — stored verbatim, embedded with MiniLM, retrieved by cosine similarity.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-secondary"><Icon name="download" size={14} /> Export</button>
          <button className="btn btn-secondary"><Icon name="trash" size={14} /> Prune stale</button>
          <button className="btn btn-primary"><Icon name="plus" size={14} /> Store pattern</button>
        </div>
      </div>

      <div className="toolbar">
        <div style={{ position: "relative", width: 280 }}>
          <input className="input" placeholder="Search name, context, approach…" value={q} onChange={e => setQ(e.target.value)} style={{ paddingLeft: 30 }} />
          <Icon name="search" size={14} className="search-icon" />
          <span style={{ position: "absolute", left: 10, top: 9, color: "var(--ink-3)" }}><Icon name="search" size={14} /></span>
        </div>
        {cats.map(c => (
          <button key={c} className={`filter-chip ${filter === c ? "active" : ""}`} onClick={() => setFilter(c)}>{c}</button>
        ))}
        <div className="spacer" />
        <span style={{ fontSize: 12, color: "var(--ink-3)", fontFamily: "var(--font-mono)" }}>{filtered.length} of {MOCK.patterns.length}</span>
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th style={{ width: 36 }}><input type="checkbox" className="checkbox" /></th>
              <th>Name</th>
              <th>Category</th>
              <th>Context</th>
              <th>Project</th>
              <th style={{ textAlign: "right" }}>Matches</th>
              <th style={{ textAlign: "right" }}>Tokens</th>
              <th>Last matched</th>
              <th style={{ width: 80 }}></th>
            </tr>
          </thead>
          <tbody>
            {rows.map(p => (
              <tr key={p.id} onClick={() => setSelected(p)}>
                <td onClick={e => e.stopPropagation()}><input type="checkbox" className="checkbox" /></td>
                <td style={{ fontFamily: "var(--font-mono)", fontSize: 12.5, fontWeight: 500 }}>{p.name}</td>
                <td><CategoryBadge cat={p.category} /></td>
                <td className="dim" style={{ maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.context}</td>
                <td className="mono">{p.project}</td>
                <td className="mono" style={{ textAlign: "right" }}>{p.match_count}</td>
                <td className="mono" style={{ textAlign: "right" }}>{p.token_count}</td>
                <td className="mono">{p.last_matched_at.split(" ")[0]}</td>
                <td onClick={e => e.stopPropagation()}>
                  <div className="row-actions">
                    <button className="icon-btn" onClick={() => setEditing(p)}><Icon name="edit" size={13} /></button>
                    <button className="icon-btn"><Icon name="trash" size={13} /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pagination {...pg} label="patterns" pageSizes={[10, 25, 50]} />
      </div>

      {selected && !editing && (
        <Drawer title={selected.name} onClose={() => setSelected(null)} footer={
          <>
            <button className="btn btn-danger"><Icon name="trash" size={13} /> Delete</button>
            <div style={{ flex: 1 }} />
            <button className="btn btn-ghost" onClick={() => setSelected(null)}>Close</button>
            <button className="btn btn-accent" onClick={() => setEditing(selected)}><Icon name="edit" size={13}/> Edit</button>
          </>
        }>
          <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
            <CategoryBadge cat={selected.category} />
            <span className="badge">id · {selected.id}</span>
            <span className="badge">{selected.token_count} tokens</span>
            <span className="badge">{selected.match_count} matches</span>
          </div>
          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", marginTop: 20, marginBottom: 6 }}>Context</h4>
          <p style={{ fontSize: 13, lineHeight: 1.55, margin: 0 }}>{selected.context}</p>
          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", marginTop: 20, marginBottom: 6 }}>Approach</h4>
          <p style={{ fontSize: 13, lineHeight: 1.55, margin: 0 }}>{selected.approach}</p>
          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", marginTop: 20, marginBottom: 6 }}>Outcome</h4>
          <p style={{ fontSize: 13, lineHeight: 1.55, margin: 0 }}>{selected.outcome}</p>
          <div className="divider" />
          <dl style={{ margin: 0 }}>
            <div className="key-value"><dt>project</dt><dd>{selected.project}</dd></div>
            <div className="key-value"><dt>last_matched_at</dt><dd>{selected.last_matched_at}</dd></div>
            <div className="key-value"><dt>embedding</dt><dd>all-MiniLM-L6-v2 · 384d</dd></div>
          </dl>
        </Drawer>
      )}

      {editing && (
        <Drawer title={`Edit · ${editing.name}`} onClose={() => setEditing(null)} footer={
          <>
            <button className="btn btn-ghost" onClick={() => setEditing(null)}>Cancel</button>
            <button className="btn btn-accent" onClick={() => { setEditing(null); setSelected(null); }}><Icon name="check" size={13}/> Save changes</button>
          </>
        }>
          <div className="form-row"><label className="form-label">name</label><input className="input mono" defaultValue={editing.name} /></div>
          <div className="form-row">
            <label className="form-label">category</label>
            <select className="select" defaultValue={editing.category}>
              {["gotcha","problem-solution","how-it-works","what-changed","discovery","decision","trade-off","general"].map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div className="form-row"><label className="form-label">context</label><textarea className="textarea" defaultValue={editing.context} /></div>
          <div className="form-row"><label className="form-label">approach</label><textarea className="textarea" defaultValue={editing.approach} /></div>
          <div className="form-row"><label className="form-label">outcome</label><textarea className="textarea" defaultValue={editing.outcome} /></div>
          <div className="form-help" style={{ padding: 10, background: "var(--bg-sunken)", borderRadius: 6 }}>
            Saving will re-embed via MiniLM (~5ms) and update match indexes.
          </div>
        </Drawer>
      )}
    </>
  );
};

/* ---- Skills page ---- */
const SkillsPage = () => {
  const [tab, setTab] = useState("suggestions");
  const trackedRows = MOCK.trackedSkills.filter(s => tab === "stale" ? s.stale : !s.stale);
  const sg = usePagination(trackedRows, 10, tab);

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Skills</h1>
          <p className="page-desc">Clusters of recurring patterns surfaced as reusable skills. Accept to generate a markdown file in .ai/skills/.</p>
        </div>
        <button className="btn btn-secondary"><Icon name="refresh" size={14} /> Re-scan</button>
      </div>

      <div className="toolbar">
        <button className={`filter-chip ${tab==="suggestions"?"active":""}`} onClick={() => setTab("suggestions")}>Suggestions · {MOCK.skillSuggestions.length}</button>
        <button className={`filter-chip ${tab==="tracked"?"active":""}`} onClick={() => setTab("tracked")}>Tracked · {MOCK.trackedSkills.filter(s=>!s.stale).length}</button>
        <button className={`filter-chip ${tab==="stale"?"active":""}`} onClick={() => setTab("stale")}>Stale · {MOCK.trackedSkills.filter(s=>s.stale).length}</button>
      </div>

      {tab === "suggestions" && (
        <div className="card">
          <div className="card-head">
            <h3 className="card-title">Pending suggestions</h3>
            <span className="card-sub">cluster threshold ≥ 0.75 · min size 3</span>
          </div>
          <div>
            {MOCK.skillSuggestions.map(s => (
              <div key={s.id} className="suggestion">
                <div className="suggestion-head">
                  <div className="suggestion-name">{s.proposed_name}</div>
                  <div className="suggestion-meta">
                    <span>{s.pattern_ids.length} patterns</span>
                    <span>·</span>
                    <span>{s.project}</span>
                    <span>·</span>
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span className="confidence-bar"><span style={{ width: `${s.confidence*100}%` }} /></span>
                      conf {s.confidence.toFixed(2)}
                    </span>
                  </div>
                </div>
                <div className="suggestion-body">{s.theme}</div>
                <div style={{ display: "flex", gap: 4, marginBottom: 10, flexWrap: "wrap" }}>
                  {s.pattern_ids.map(pid => <span key={pid} className="tag">#{pid}</span>)}
                </div>
                <div className="suggestion-actions">
                  <button className="btn btn-accent btn-sm"><Icon name="check" size={12} /> Accept</button>
                  <button className="btn btn-secondary btn-sm">Defer</button>
                  <button className="btn btn-ghost btn-sm">Dismiss</button>
                  <div style={{ flex: 1 }} />
                  <button className="btn btn-ghost btn-sm">Preview markdown</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {(tab === "tracked" || tab === "stale") && (
        <div className="card">
          <table className="table">
            <thead>
              <tr>
                <th>Name</th><th>Path</th><th>Source</th>
                <th style={{ textAlign: "right" }}>Matches</th>
                <th>Last matched</th><th></th>
              </tr>
            </thead>
            <tbody>
              {sg.slice.map(s => (
                <tr key={s.id}>
                  <td style={{ fontWeight: 500 }}>{s.name}</td>
                  <td className="mono" style={{ color: "var(--ink-3)" }}>{s.path}</td>
                  <td><span className="badge">{s.source}</span></td>
                  <td className="mono" style={{ textAlign: "right" }}>{s.match_count}</td>
                  <td className="mono">{s.last_matched}</td>
                  <td>
                    <div className="row-actions">
                      <button className="icon-btn"><Icon name="external" size={13} /></button>
                      <button className="icon-btn"><Icon name="trash" size={13} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination {...sg} label="skills" pageSizes={[10, 25, 50]} />
        </div>
      )}
    </>
  );
};

/* ---- Bug Hunter summary card (Summary page widget) ---- */
const BugHunterCard = ({ onOpen }) => {
  const r = BUG_REPORT;
  const bugsByS = { Critical: 0, High: 0, Medium: 0, Low: 0 };
  r.bugs.forEach(b => bugsByS[b.severity]++);
  const healthColor = r.summary.health_score >= 85 ? "var(--success)"
                   : r.summary.health_score >= 60 ? "var(--warning)"
                   : "var(--danger)";
  // mini trend path
  const hist = r.trend.history;
  const w = 120, he = 32;
  const scores = hist.map(h => h.health);
  const mn = Math.min(...scores) - 4, mx = Math.max(...scores) + 4;
  const xs = hist.length;
  const toX = i => (i / (xs - 1)) * (w - 4) + 2;
  const toY = v => he - 2 - ((v - mn) / (mx - mn)) * (he - 4);
  const path = scores.map((v, i) => `${i === 0 ? "M" : "L"}${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");

  return (
    <div className="card bug-hunter-card" onClick={onOpen} role="button" tabIndex={0}
      onKeyDown={e => (e.key === "Enter" || e.key === " ") && onOpen && onOpen()}
      style={{ cursor: "pointer" }}>
      <div className="card-head">
        <h3 className="card-title">
          <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
            <Icon name="bug-report" size={14} /> Bug Hunter
          </span>
        </h3>
        <span className={`badge ${r.ci.status === "PASS" ? "badge-success" : "badge-danger"}`} style={{ fontSize: 10.5 }}>
          {r.ci.status === "PASS" ? <><Icon name="check" size={10} /> CI PASS</> : "CI FAIL"}
        </span>
      </div>
      <div style={{ padding: "14px 16px" }}>
        <div style={{ display: "grid", gridTemplateColumns: "auto 1fr", gap: 14, alignItems: "center" }}>
          {/* score */}
          <div style={{ textAlign: "center" }}>
            <div style={{
              fontSize: 34, fontWeight: 600, letterSpacing: "-0.02em",
              fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums",
              color: healthColor, lineHeight: 1,
            }}>{r.summary.health_score}</div>
            <div style={{ fontSize: 10.5, color: "var(--ink-3)", fontFamily: "var(--font-mono)", marginTop: 2, letterSpacing: "0.04em" }}>
              /100 · {r.summary.rating.toLowerCase()}
            </div>
          </div>
          {/* trend */}
          <div>
            <svg width="100%" height={he} viewBox={`0 0 ${w} ${he}`} preserveAspectRatio="none" style={{ display: "block" }}>
              <path d={`${path} L${toX(xs-1).toFixed(1)},${he} L${toX(0).toFixed(1)},${he} Z`} fill={healthColor} opacity="0.12" />
              <path d={path} fill="none" stroke={healthColor} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              {scores.map((v, i) => (
                <circle key={i} cx={toX(i)} cy={toY(v)} r={i === xs - 1 ? 2.5 : 1.5} fill={healthColor} />
              ))}
            </svg>
            <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--success)", marginTop: 2 }}>
              <Icon name="arrow-up" size={10} /> +{r.trend.change} vs. last scan · {r.trend.direction}
            </div>
          </div>
        </div>

        {/* severity row */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6, marginTop: 14 }}>
          {["Critical", "High", "Medium", "Low"].map(s => {
            const c = SEV_COLOR[s];
            return (
              <div key={s} style={{ background: c.bg, padding: "6px 8px", borderRadius: 4, textAlign: "center" }}>
                <div style={{ fontSize: 9.5, textTransform: "uppercase", letterSpacing: "0.06em", color: c.fg, fontWeight: 600, opacity: 0.85 }}>{s}</div>
                <div style={{ fontSize: 15, fontFamily: "var(--font-mono)", fontWeight: 600, color: c.fg, lineHeight: 1.2 }}>{bugsByS[s]}</div>
              </div>
            );
          })}
        </div>

        {/* counts footer */}
        <div style={{ display: "flex", gap: 12, marginTop: 12, fontSize: 11.5, color: "var(--ink-3)", fontFamily: "var(--font-mono)" }}>
          <span><b style={{ color: "var(--ink-1)" }}>{r.summary.total_bugs}</b> bugs</span>
          <span><b style={{ color: "var(--ink-1)" }}>{r.summary.code_smells}</b> smells</span>
          <span><b style={{ color: "var(--ink-1)" }}>{r.tests.passed}</b>/{r.tests.passed + r.tests.failed} tests</span>
          <div style={{ flex: 1 }} />
          <span>scanned {r.generated_at.split(" ")[0]}</span>
        </div>

        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <span style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{r.branch}@{r.commit}</span>
          <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, fontWeight: 500, color: "var(--accent-600)" }}>
            View full report <Icon name="chevron-right" size={12} />
          </span>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { SummaryPage, PatternsPage, SkillsPage, BugHunterCard });
