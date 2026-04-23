/* ensemble-mcp — Projects, Drift, Sessions pages */

const ProjectsPage = () => {
  const [selected, setSelected] = useState(null);
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const data = await API.projects();
        if (cancelled) return;
        setProjects(data.projects || []);
      } catch (e) { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [refreshKey]);

  const pg = usePagination(projects, 6);

  const handleReindex = async (path) => {
    try { await API.projectReindex(path); setRefreshKey(k => k + 1); } catch (e) { alert(e.message); }
  };
  const handleDelete = async (path) => {
    try { await API.projectDelete(path); setSelected(null); setRefreshKey(k => k + 1); } catch (e) { alert(e.message); }
  };

  if (loading) return <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>Loading projects…</div>;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Projects</h1>
          <p className="page-desc">Indexed codebases. File counts, language breakdown, and index staleness.</p>
        </div>
        <button className="btn btn-primary"><Icon name="plus" size={14} /> Index project</button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))", gap: 12 }}>
        {pg.slice.map(p => {
          const name = p.project_path ? p.project_path.split("/").slice(-2).join("/") : p.project_path;
          return (
            <div key={p.project_path} className="card" onClick={() => setSelected(p)} style={{ cursor: "pointer" }}>
              <div style={{ padding: "14px 16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600 }}>{name}</div>
                  <span className="badge badge-success"><Icon name="check" size={10}/> indexed</span>
                </div>
                <div style={{ fontSize: 11, color: "var(--ink-4)", fontFamily: "var(--font-mono)", marginBottom: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.project_path}</div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginBottom: 14 }}>
                  <div><div style={{ fontSize: 10.5, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>Files</div><div style={{ fontSize: 15, fontFamily: "var(--font-mono)", fontWeight: 600 }}>{(p.file_count || 0).toLocaleString()}</div></div>
                  <div><div style={{ fontSize: 10.5, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>Languages</div><div style={{ fontSize: 15, fontFamily: "var(--font-mono)", fontWeight: 600 }}>{p.language_count || 0}</div></div>
                  <div><div style={{ fontSize: 10.5, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>Indexed</div><div style={{ fontSize: 11, fontFamily: "var(--font-mono)" }}>{(p.last_indexed || "—").split("T")[0]}</div></div>
                </div>

                <div style={{ marginTop: 12, display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--ink-3)", fontFamily: "var(--font-mono)" }}>
                  <span>indexed {p.last_indexed || "—"}</span>
                </div>
              </div>
            </div>
          );
        })}
        {projects.length === 0 && <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>No indexed projects</div>}
      </div>

      {projects.length > pg.pageSize && (
        <div className="card" style={{ marginTop: 12 }}>
          <Pagination {...pg} label="projects" pageSizes={[6, 12, 24]} />
        </div>
      )}

      {selected && (
        <ProjectDrawer project={selected} onClose={() => setSelected(null)} onReindex={handleReindex} onDelete={handleDelete} />
      )}
    </>
  );
};

/** Drawer for project detail — fetches detail on open. */
const ProjectDrawer = ({ project, onClose, onReindex, onDelete }) => {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const d = await API.projectDetail(project.project_path);
        if (!cancelled) setDetail(d);
      } catch (e) { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [project.project_path]);

  const name = project.project_path ? project.project_path.split("/").slice(-2).join("/") : project.project_path;

  return (
    <Drawer title={name} onClose={onClose} footer={
      <>
        <button className="btn btn-danger" onClick={() => onDelete(project.project_path)}><Icon name="trash" size={13}/> Delete index</button>
        <div style={{ flex: 1 }} />
        <button className="btn btn-ghost" onClick={onClose}>Close</button>
        <button className="btn btn-accent" onClick={() => onReindex(project.project_path)}><Icon name="refresh" size={13}/> Re-index</button>
      </>
    }>
      <dl style={{ margin: 0, marginBottom: 20 }}>
        <div className="key-value"><dt>path</dt><dd>{project.project_path}</dd></div>
        <div className="key-value"><dt>files</dt><dd>{(detail?.total_files || project.file_count || 0).toLocaleString()}</dd></div>
        <div className="key-value"><dt>exports</dt><dd>{(detail?.total_exports || 0).toLocaleString()}</dd></div>
        <div className="key-value"><dt>last_indexed</dt><dd>{project.last_indexed || "—"}</dd></div>
        <div className="key-value"><dt>status</dt><dd><span className="badge badge-success">indexed</span></dd></div>
      </dl>
      {loading ? (
        <div style={{ padding: 20, textAlign: "center", color: "var(--ink-3)" }}>Loading detail…</div>
      ) : detail && detail.languages ? (
        <>
          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "0 0 10px" }}>Language breakdown</h4>
          <LangBar languages={Object.fromEntries(detail.languages.map(l => [l.language, l.count]))} />
          <div style={{ marginTop: 12 }}>
            {detail.languages.map(l => (
              <div key={l.language} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", fontSize: 12.5, fontFamily: "var(--font-mono)", borderBottom: "1px dashed var(--border)" }}>
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: langColor(l.language) }} /> {l.language}
                </span>
                <span style={{ color: "var(--ink-3)" }}>{l.count} files · {Math.round(l.count/(detail.total_files||1)*100)}%</span>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </Drawer>
  );
};

/* ---- Drift page ---- */
const DriftPage = () => {
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("all");
  const [driftChecks, setDriftChecks] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const data = await API.drift({ limit: 200 });
        if (cancelled) return;
        setDriftChecks(data.drift_checks || []);
      } catch (e) { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  const rows = driftChecks.filter(d => filter === "all" || d.verdict === filter);
  const pg = usePagination(rows, 10, filter);

  const aligned = driftChecks.filter(d => d.verdict === "aligned").length;
  const minor = driftChecks.filter(d => d.verdict === "minor_drift").length;
  const major = driftChecks.filter(d => d.verdict === "significant_drift").length;
  const total = driftChecks.length;

  if (loading) return <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>Loading drift checks…</div>;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Drift</h1>
          <p className="page-desc">Cosine distance between task description and diff summary. Below 0.3 aligned, below 0.6 minor, above significant.</p>
        </div>
      </div>

      <div className="stat-grid" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <div className="stat"><div className="stat-label">Total</div><div className="stat-value">{total}</div></div>
        <div className="stat"><div className="stat-label" style={{ color: "var(--success)" }}>Aligned</div><div className="stat-value">{aligned}<span className="stat-unit">/{total}</span></div><div className="stat-delta">{total > 0 ? Math.round(aligned/total*100) : 0}% of recent</div></div>
        <div className="stat"><div className="stat-label" style={{ color: "var(--warning)" }}>Minor drift</div><div className="stat-value">{minor}<span className="stat-unit">/{total}</span></div></div>
        <div className="stat"><div className="stat-label" style={{ color: "var(--danger)" }}>Significant</div><div className="stat-value">{major}<span className="stat-unit">/{total}</span></div></div>
      </div>

      <div className="toolbar">
        {["all","aligned","minor_drift","significant_drift"].map(f => (
          <button key={f} className={`filter-chip ${filter === f ? "active" : ""}`} onClick={() => setFilter(f)}>{f.replace("_"," ")}</button>
        ))}
        <div className="spacer" />
        <span style={{ fontSize: 12, color: "var(--ink-3)", fontFamily: "var(--font-mono)" }}>thresholds · aligned &lt; 0.2 · minor &lt; 0.5</span>
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Task</th><th>Project</th><th>Score</th><th>Verdict</th><th>Files</th><th>Flags</th><th>When</th>
            </tr>
          </thead>
          <tbody>
            {pg.slice.map(d => (
              <tr key={d.id} onClick={() => setSelected(d)}>
                <td style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.task_description}</td>
                <td className="mono">{d.project}</td>
                <td>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
                    <span className="score-track">
                      <span className={d.verdict === "aligned" ? "seg-aligned" : d.verdict === "minor_drift" ? "seg-minor" : "seg-major"} style={{ width: `${d.score*100}%` }} />
                    </span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontVariantNumeric: "tabular-nums" }}>{d.score.toFixed(2)}</span>
                  </span>
                </td>
                <td><VerdictBadge v={d.verdict} /></td>
                <td className="mono">{d.changed_files.length}</td>
                <td>{d.flags.length > 0 ? <span className="badge badge-warning">{d.flags.length}</span> : <span style={{ color: "var(--ink-4)" }}>—</span>}</td>
                <td className="mono dim">{(d.created_at || "").split(" ")[1] || (d.created_at || "").split("T")[1]?.slice(0,8) || "—"}</td>
              </tr>
            ))}
            {pg.slice.length === 0 && <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--ink-3)", padding: 20 }}>No drift checks</td></tr>}
          </tbody>
        </table>
        <Pagination {...pg} label="drift checks" />
      </div>

      {selected && (
        <Drawer title={`Drift check #${selected.id}`} onClose={() => setSelected(null)}>
          <div style={{ marginBottom: 16 }}>
            <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "0 0 6px" }}>Task</h4>
            <p style={{ margin: 0, fontSize: 13 }}>{selected.task_description}</p>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 20 }}>
            <div className="stat"><div className="stat-label">Score</div><div className="stat-value">{selected.score.toFixed(2)}</div></div>
            <div className="stat"><div className="stat-label">Similarity</div><div className="stat-value">{selected.similarity.toFixed(2)}</div></div>
          </div>
          <div><VerdictBadge v={selected.verdict} /></div>
          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>Changed files</h4>
          <div>
            {selected.changed_files.map(f => (
              <div key={f} style={{ padding: "6px 10px", background: "var(--bg-sunken)", borderRadius: 4, fontFamily: "var(--font-mono)", fontSize: 12, marginBottom: 4 }}>{f}</div>
            ))}
          </div>
          {selected.flags.length > 0 && (
            <>
              <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--warning)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>Flags</h4>
              {selected.flags.map((f, i) => (
                <div key={i} style={{ padding: "8px 10px", background: "var(--warning-bg)", color: "var(--warning)", borderRadius: 4, fontSize: 12.5, marginBottom: 4 }}>{f}</div>
              ))}
            </>
          )}
        </Drawer>
      )}
    </>
  );
};

/* ---- Sessions page ---- */
const SessionsPage = () => {
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("all");
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [detailData, setDetailData] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const data = await API.sessions({ limit: 200 });
        if (cancelled) return;
        setSessions(data.sessions || []);
      } catch (e) { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  // Fetch detail when a session is selected
  useEffect(() => {
    if (!selected) { setDetailData(null); return; }
    let cancelled = false;
    (async () => {
      try {
        const d = await API.sessionDetail(selected.session_id);
        if (!cancelled) setDetailData(d);
      } catch (e) { /* silent */ }
    })();
    return () => { cancelled = true; };
  }, [selected?.session_id]);

  const rows = sessions.filter(s => filter === "all" || s.status === filter);
  const pg = usePagination(rows, 10, filter);

  if (loading) return <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>Loading sessions…</div>;

  // Use detail data for the drawer if available, otherwise fall back to list item
  const drawerSession = detailData || selected;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Sessions</h1>
          <p className="page-desc">Pipeline checkpoints with optimistic versioning. Search by semantic similarity against original_request.</p>
        </div>
      </div>

      <div className="toolbar">
        {["all","running","completed","failed"].map(f => (
          <button key={f} className={`filter-chip ${filter === f ? "active" : ""}`} onClick={() => setFilter(f)}>{f}</button>
        ))}
      </div>

      <div className="card">
        <table className="table">
          <thead>
            <tr>
              <th>Session</th><th>Original request</th><th>Status</th><th>Class</th><th>Project</th>
              <th style={{ textAlign: "right" }}>Version</th><th>Created</th>
            </tr>
          </thead>
          <tbody>
            {pg.slice.map(s => (
              <tr key={s.session_id} onClick={() => setSelected(s)}>
                <td className="mono" style={{ fontWeight: 500 }}>{s.session_id}</td>
                <td style={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.original_request || "—"}</td>
                <td><StatusBadge s={s.status} /></td>
                <td><span className="badge">{s.task_classification || "—"}</span></td>
                <td className="mono">{s.project || "—"}</td>
                <td className="mono" style={{ textAlign: "right" }}>v{s.version}</td>
                <td className="mono dim">{(s.created_at || "").split(" ")[1] || (s.created_at || "").split("T")[1]?.slice(0,8) || "—"}</td>
              </tr>
            ))}
            {pg.slice.length === 0 && <tr><td colSpan={7} style={{ textAlign: "center", color: "var(--ink-3)", padding: 20 }}>No sessions</td></tr>}
          </tbody>
        </table>
        <Pagination {...pg} label="sessions" />
      </div>

      {selected && drawerSession && (
        <Drawer title={drawerSession.session_id} onClose={() => setSelected(null)} footer={
          <>
            {drawerSession.status === "running" && <button className="btn btn-danger">Kill session</button>}
            <div style={{ flex: 1 }} />
            <button className="btn btn-secondary"><Icon name="copy" size={13} /> Copy ID</button>
            <button className="btn btn-accent">Resume</button>
          </>
        }>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
            <StatusBadge s={drawerSession.status} />
            {drawerSession.task_classification && <span className="badge">{drawerSession.task_classification}</span>}
            <span className="badge">v{drawerSession.version}</span>
            {drawerSession.state?.model_tier && <TierBadge t={drawerSession.state.model_tier} />}
          </div>

          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "0 0 6px" }}>Original request</h4>
          <p style={{ margin: 0, fontSize: 13.5, fontWeight: 500 }}>{drawerSession.original_request || "—"}</p>

          {drawerSession.state?.completed_steps && (
            <>
              <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 8px" }}>Progress</h4>
              <div>
                {(drawerSession.state.completed_steps || []).map(s => <span key={s} className="step-chip done"><Icon name="check" size={10}/> {s}</span>)}
                {(drawerSession.state.remaining_steps || []).map(s => <span key={s} className="step-chip pending">{s}</span>)}
              </div>
            </>
          )}

          {drawerSession.state?.decisions && drawerSession.state.decisions.length > 0 && <>
            <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>Decisions</h4>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.6 }}>
              {drawerSession.state.decisions.map((d, i) => <li key={i}>{d}</li>)}
            </ul>
          </>}

          {drawerSession.state?.files_changed && drawerSession.state.files_changed.length > 0 && <>
            <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>Files changed</h4>
            <div>
              {drawerSession.state.files_changed.map(f => <div key={f} style={{ padding: "5px 10px", background: "var(--bg-sunken)", borderRadius: 4, fontFamily: "var(--font-mono)", fontSize: 12, marginBottom: 4 }}>{f}</div>)}
            </div>
          </>}

          {drawerSession.state?.errors && drawerSession.state.errors.length > 0 && <>
            <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--danger)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>Errors</h4>
            {drawerSession.state.errors.map((e, i) => <div key={i} style={{ padding: "8px 10px", background: "var(--danger-bg)", color: "var(--danger)", borderRadius: 4, fontSize: 12.5, marginBottom: 4 }}>{e}</div>)}
          </>}

          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>State snapshot</h4>
          <JsonView value={drawerSession.state || {}} />
        </Drawer>
      )}
    </>
  );
};

Object.assign(window, { ProjectsPage, ProjectDrawer, DriftPage, SessionsPage });
