/* ensemble-mcp — Summary, Patterns, Skills pages */

const SummaryPage = ({ onNavigate }) => {
  const [summary, setSummary] = useState(null);
  const [health, setHealth] = useState(null);
  const [activity, setActivity] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [bugSummary, setBugSummary] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [s, h, rs] = await Promise.all([API.summary(), API.health(), API.reportsSummary().catch(() => null)]);
        if (cancelled) return;
        setSummary(s);
        setHealth(h);
        setActivity(s.recent_activity || []);
        setBugSummary(rs);
      } catch (e) { if (!cancelled) setError(e.message); }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  // Transform recent_activity from API shape to display shape
  // (must be above early returns so usePagination hook is always called)
  const displayActivity = activity.map(a => ({
    tool: a.tool_name,
    project: "—",
    duration_ms: a.duration_ms,
    ts: a.called_at ? a.called_at.split(" ").pop() || a.called_at.split("T").pop()?.slice(0,8) || a.called_at : "—",
    ok: true,
  }));
  const act = usePagination(displayActivity, 20, "recent");

  if (loading) return <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>Loading summary…</div>;
  if (error) return <div style={{ padding: 40, textAlign: "center", color: "var(--danger)" }}>Error: {error}</div>;

  const s = summary;
  const h = health;

  const patternDelta = (() => {
    const g = s.pattern_growth_30d;
    if (!g || g.length < 7) return null;
    const last7 = g.slice(-7).reduce((a, b) => a + b, 0);
    return last7 > 0 ? `+${last7} this week` : `${last7} this week`;
  })();

  const stats = [
    { label: "Patterns",   value: s.pattern_count,      delta: patternDelta, up: patternDelta && patternDelta.startsWith("+"),  spark: s.pattern_growth_30d },
    { label: "Skills",     value: s.active_skills,      sub: `${s.pending_skills} pending`, spark: null },
    { label: "Projects",   value: s.project_count,      sub: `${s.project_count} indexed`,    spark: null },
    { label: "Drift / 30d",value: s.drift_checks_30d,   delta: "30d window",    spark: s.pattern_growth_30d },
    { label: "Sessions",   value: s.session_count,      sub: `${s.sessions_running || 0} running · ${s.sessions_completed || 0} done`, spark: [2,3,3,4,5,5,6,7,s.session_count] },
    { label: "MCP calls today", value: (s.calls_today || 0).toLocaleString(), delta: "last 24h", up: true, spark: s.calls_7d || [] },
  ];

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Summary</h1>
          <p className="page-desc">Aggregate state of the local ensemble-mcp server. All processing is local — SQLite + ONNX, zero cloud calls.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost" onClick={() => location.reload()}><Icon name="refresh" size={14} /> Refresh</button>
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
            <span className="card-sub">{displayActivity.length} logged · live</span>
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
            {displayActivity.length === 0 && <div style={{ padding: 20, textAlign: "center", color: "var(--ink-3)" }}>No recent calls</div>}
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
              {s.calls_by_hour && s.calls_by_hour.length > 0 ? (
                <>
                  <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 80, marginBottom: 6 }}>
                    {s.calls_by_hour.map((v, i) => {
                      const max = Math.max(...s.calls_by_hour, 1);
                      const barH = Math.max(2, (v / max) * 72);
                      const isPeak = v === max && v > 0;
                      return (
                        <div key={i} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 2 }}>
                          <div style={{
                            width: "100%", height: `${barH}px`,
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
                </>
              ) : (
                <div style={{ padding: 20, textAlign: "center", color: "var(--ink-3)" }}>No call data</div>
              )}
            </div>
          </div>

          <BugHunterCard onOpen={() => onNavigate && onNavigate("bug-report")} bugSummary={bugSummary} />

          <div className="card">
            <div className="card-head"><h3 className="card-title"><Icon name="database" size={14} /> Server health</h3></div>
            <div className="card-body">
              <dl style={{ margin: 0 }}>
                <div className="key-value"><dt>status</dt><dd><span className="badge badge-success"><Icon name="check" size={10}/> {h.status}</span></dd></div>
                <div className="key-value"><dt>version</dt><dd>{h.version}</dd></div>
                <div className="key-value"><dt>db_size</dt><dd>{fmtBytes(h.db_size_bytes)}</dd></div>
                <div className="key-value"><dt>patterns</dt><dd>{h.pattern_count}</dd></div>
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
  const [patterns, setPatterns] = useState([]);
  const [totalPatterns, setTotalPatterns] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const data = await API.patterns({ limit: 200, category: filter !== "all" ? filter : undefined });
        if (cancelled) return;
        setPatterns(data.patterns || []);
        setTotalPatterns(data.total || 0);
      } catch (e) { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [filter, refreshKey]);

  const cats = ["all", "problem-solution", "how-it-works", "gotcha", "decision", "trade-off", "what-changed", "discovery"];
  const filtered = useMemo(() => {
    return patterns.filter(p =>
      (!q || (p.name && p.name.includes(q)) || (p.context && p.context.toLowerCase().includes(q.toLowerCase())))
    );
  }, [patterns, q]);
  const pg = usePagination(filtered, 10, `${filter}|${q}`);
  const rows = pg.slice;

  const handleDelete = async (id) => {
    try { await API.patternDelete(id); setRefreshKey(k => k + 1); setSelected(null); } catch (e) { alert(e.message); }
  };
  const handlePrune = async () => {
    try { await API.patternsPrune(90); setRefreshKey(k => k + 1); } catch (e) { alert(e.message); }
  };
  const handleSave = async (p, form) => {
    try {
      await API.patternUpdate(p.id, form);
      setEditing(null); setSelected(null); setRefreshKey(k => k + 1);
    } catch (e) { alert(e.message); }
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Patterns</h1>
          <p className="page-desc">Semantic memory of past solutions — stored verbatim, embedded with MiniLM, retrieved by cosine similarity.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-secondary"><Icon name="download" size={14} /> Export</button>
          <button className="btn btn-secondary" onClick={handlePrune}><Icon name="trash" size={14} /> Prune stale</button>
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
        <span style={{ fontSize: 12, color: "var(--ink-3)", fontFamily: "var(--font-mono)" }}>{filtered.length} of {totalPatterns}</span>
      </div>

      {loading ? (
        <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>Loading patterns…</div>
      ) : (
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
                <td className="mono" style={{ textAlign: "right" }}>{p.token_count || "—"}</td>
                <td className="mono">{(p.last_matched_at || "—").split(" ")[0]}</td>
                <td onClick={e => e.stopPropagation()}>
                  <div className="row-actions">
                    <button className="icon-btn" onClick={() => setEditing(p)}><Icon name="edit" size={13} /></button>
                    <button className="icon-btn" onClick={() => handleDelete(p.id)}><Icon name="trash" size={13} /></button>
                  </div>
                </td>
              </tr>
            ))}
            {rows.length === 0 && <tr><td colSpan={9} style={{ textAlign: "center", color: "var(--ink-3)", padding: 20 }}>No patterns found</td></tr>}
          </tbody>
        </table>
        <Pagination {...pg} label="patterns" pageSizes={[10, 25, 50]} />
      </div>
      )}

      {selected && !editing && (
        <Drawer title={selected.name} onClose={() => setSelected(null)} footer={
          <>
            <button className="btn btn-danger" onClick={() => handleDelete(selected.id)}><Icon name="trash" size={13} /> Delete</button>
            <div style={{ flex: 1 }} />
            <button className="btn btn-ghost" onClick={() => setSelected(null)}>Close</button>
            <button className="btn btn-accent" onClick={() => setEditing(selected)}><Icon name="edit" size={13}/> Edit</button>
          </>
        }>
          <div style={{ display: "flex", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
            <CategoryBadge cat={selected.category} />
            <span className="badge">id · {selected.id}</span>
            {selected.token_count && <span className="badge">{selected.token_count} tokens</span>}
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
        <PatternEditDrawer pattern={editing} onClose={() => setEditing(null)} onSave={handleSave} />
      )}
    </>
  );
};

/** Edit drawer for patterns — uses refs to collect form values. */
const PatternEditDrawer = ({ pattern, onClose, onSave }) => {
  const nameRef = useRef(null);
  const catRef = useRef(null);
  const ctxRef = useRef(null);
  const appRef = useRef(null);
  const outRef = useRef(null);

  const save = () => {
    onSave(pattern, {
      name: nameRef.current.value,
      category: catRef.current.value,
      context: ctxRef.current.value,
      approach: appRef.current.value,
      outcome: outRef.current.value,
    });
  };

  return (
    <Drawer title={`Edit · ${pattern.name}`} onClose={onClose} footer={
      <>
        <button className="btn btn-ghost" onClick={onClose}>Cancel</button>
        <button className="btn btn-accent" onClick={save}><Icon name="check" size={13}/> Save changes</button>
      </>
    }>
      <div className="form-row"><label className="form-label">name</label><input ref={nameRef} className="input mono" defaultValue={pattern.name} /></div>
      <div className="form-row">
        <label className="form-label">category</label>
        <select ref={catRef} className="select" defaultValue={pattern.category}>
          {["gotcha","problem-solution","how-it-works","what-changed","discovery","decision","trade-off","general"].map(c => <option key={c}>{c}</option>)}
        </select>
      </div>
      <div className="form-row"><label className="form-label">context</label><textarea ref={ctxRef} className="textarea" defaultValue={pattern.context} /></div>
      <div className="form-row"><label className="form-label">approach</label><textarea ref={appRef} className="textarea" defaultValue={pattern.approach} /></div>
      <div className="form-row"><label className="form-label">outcome</label><textarea ref={outRef} className="textarea" defaultValue={pattern.outcome} /></div>
      <div className="form-help" style={{ padding: 10, background: "var(--bg-sunken)", borderRadius: 6 }}>
        Saving will re-embed via MiniLM (~5ms) and update match indexes.
      </div>
    </Drawer>
  );
};

/* ---- Skills page ---- */
const SkillsPage = () => {
  const [tab, setTab] = useState("suggestions");
  const [suggestions, setSuggestions] = useState([]);
  const [tracked, setTracked] = useState([]);
  const [staleSkills, setStaleSkills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const [skillsData, staleData] = await Promise.all([
          API.skills(),
          API.skillsStale().catch(() => ({ stale_skills: [] })),
        ]);
        if (cancelled) return;
        setSuggestions(skillsData.suggestions || []);
        setTracked(skillsData.tracked || []);
        setStaleSkills(staleData.stale_skills || []);
      } catch (e) { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [refreshKey]);

  const pendingSuggestions = suggestions.filter(s => s.status === "pending");
  const activeTracked = tracked.filter(t => {
    const staleIds = new Set(staleSkills.map(s => s.skill_path));
    return !staleIds.has(t.skill_path);
  });
  const staleTracked = tracked.filter(t => {
    const staleIds = new Set(staleSkills.map(s => s.skill_path));
    return staleIds.has(t.skill_path);
  });

  const displayTracked = tab === "stale" ? staleTracked : activeTracked;
  const sg = usePagination(displayTracked, 10, tab);

  const handleAction = async (id, action) => {
    try { await API.skillAction(id, action); setRefreshKey(k => k + 1); } catch (e) { alert(e.message); }
  };
  const handleDeleteTracked = async (id) => {
    try { await API.skillDelete(id); setRefreshKey(k => k + 1); } catch (e) { alert(e.message); }
  };

  if (loading) return <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>Loading skills…</div>;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Skills</h1>
          <p className="page-desc">Clusters of recurring patterns surfaced as reusable skills. Accept to generate a markdown file in .ai/skills/.</p>
        </div>
        <button className="btn btn-secondary" onClick={() => setRefreshKey(k => k + 1)}><Icon name="refresh" size={14} /> Re-scan</button>
      </div>

      <div className="toolbar">
        <button className={`filter-chip ${tab==="suggestions"?"active":""}`} onClick={() => setTab("suggestions")}>Suggestions · {pendingSuggestions.length}</button>
        <button className={`filter-chip ${tab==="tracked"?"active":""}`} onClick={() => setTab("tracked")}>Tracked · {activeTracked.length}</button>
        <button className={`filter-chip ${tab==="stale"?"active":""}`} onClick={() => setTab("stale")}>Stale · {staleTracked.length}</button>
      </div>

      {tab === "suggestions" && (
        <div className="card">
          <div className="card-head">
            <h3 className="card-title">Pending suggestions</h3>
            <span className="card-sub">cluster threshold ≥ 0.75 · min size 3</span>
          </div>
          <div>
            {pendingSuggestions.length === 0 && <div style={{ padding: 20, textAlign: "center", color: "var(--ink-3)" }}>No pending suggestions</div>}
            {pendingSuggestions.map(s => (
              <div key={s.id} className="suggestion">
                <div className="suggestion-head">
                  <div className="suggestion-name">{s.proposed_name}</div>
                  <div className="suggestion-meta">
                    <span>{s.project}</span>
                    <span>·</span>
                    <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span className="confidence-bar"><span style={{ width: `${(s.confidence || 0)*100}%` }} /></span>
                      conf {(s.confidence || 0).toFixed(2)}
                    </span>
                  </div>
                </div>
                <div className="suggestion-body">{s.theme}</div>
                <div className="suggestion-actions">
                  <button className="btn btn-accent btn-sm" onClick={() => handleAction(s.id, "accept")}><Icon name="check" size={12} /> Accept</button>
                  <button className="btn btn-secondary btn-sm" onClick={() => handleAction(s.id, "defer")}>Defer</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => handleAction(s.id, "dismiss")}>Dismiss</button>
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
              {sg.slice.map(s => {
                const name = s.skill_path ? s.skill_path.split("/").pop().replace(/\.md$/, "") : `skill-${s.id}`;
                const source = s.skill_path?.includes(".claude/") ? "claude" : s.skill_path?.includes(".cursor/") ? "cursor" : "opencode";
                return (
                  <tr key={s.id}>
                    <td style={{ fontWeight: 500 }}>{name}</td>
                    <td className="mono" style={{ color: "var(--ink-3)" }}>{s.skill_path}</td>
                    <td><span className="badge">{source}</span></td>
                    <td className="mono" style={{ textAlign: "right" }}>{s.match_count}</td>
                    <td className="mono">{s.last_matched_at || "—"}</td>
                    <td>
                      <div className="row-actions">
                        <button className="icon-btn"><Icon name="external" size={13} /></button>
                        <button className="icon-btn" onClick={() => handleDeleteTracked(s.id)}><Icon name="trash" size={13} /></button>
                      </div>
                    </td>
                  </tr>
                );
              })}
              {sg.slice.length === 0 && <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--ink-3)", padding: 20 }}>No skills</td></tr>}
            </tbody>
          </table>
          <Pagination {...sg} label="skills" pageSizes={[10, 25, 50]} />
        </div>
      )}
    </>
  );
};

/* ---- Bug Hunter summary card (Summary page widget) ---- */
const BugHunterCard = ({ onOpen, bugSummary }) => {
  // If no bug report data available, show a placeholder
  if (!bugSummary || !bugSummary.available) {
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
        </div>
        <div style={{ padding: "20px 16px", textAlign: "center", color: "var(--ink-3)" }}>
          No bug reports available
        </div>
      </div>
    );
  }

  const healthScore = bugSummary.health_score || 0;
  const trend = bugSummary.trend || "stable";
  const healthColor = healthScore >= 85 ? "var(--success)"
                   : healthScore >= 60 ? "var(--warning)"
                   : "var(--danger)";

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
      </div>
      <div style={{ padding: "14px 16px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <div style={{ textAlign: "center" }}>
            <div style={{
              fontSize: 34, fontWeight: 600, letterSpacing: "-0.02em",
              fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums",
              color: healthColor, lineHeight: 1,
            }}>{healthScore}</div>
            <div style={{ fontSize: 10.5, color: "var(--ink-3)", fontFamily: "var(--font-mono)", marginTop: 2, letterSpacing: "0.04em" }}>
              /100 · {trend}
            </div>
          </div>
        </div>
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)", display: "flex", alignItems: "center", justifyContent: "flex-end" }}>
          <span style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, fontWeight: 500, color: "var(--accent-600)" }}>
            View full report <Icon name="chevron-right" size={12} />
          </span>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { SummaryPage, PatternsPage, SkillsPage, BugHunterCard, PatternEditDrawer });
