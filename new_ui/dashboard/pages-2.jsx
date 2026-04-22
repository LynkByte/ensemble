/* ensemble-mcp — Projects, Drift, Sessions pages */

const ProjectsPage = () => {
  const [selected, setSelected] = useState(null);
  const pg = usePagination(MOCK.projects, 6);
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
        {pg.slice.map(p => (
          <div key={p.path} className="card" onClick={() => setSelected(p)} style={{ cursor: "pointer" }}>
            <div style={{ padding: "14px 16px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 4 }}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600 }}>{p.name}</div>
                {p.stale
                  ? <span className="badge badge-warning">stale</span>
                  : <span className="badge badge-success"><Icon name="check" size={10}/> healthy</span>}
              </div>
              <div style={{ fontSize: 11, color: "var(--ink-4)", fontFamily: "var(--font-mono)", marginBottom: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.path}</div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 14 }}>
                <div><div style={{ fontSize: 10.5, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>Files</div><div style={{ fontSize: 15, fontFamily: "var(--font-mono)", fontWeight: 600 }}>{p.files.toLocaleString()}</div></div>
                <div><div style={{ fontSize: 10.5, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>Patterns</div><div style={{ fontSize: 15, fontFamily: "var(--font-mono)", fontWeight: 600 }}>{p.patterns}</div></div>
                <div><div style={{ fontSize: 10.5, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>Drifts</div><div style={{ fontSize: 15, fontFamily: "var(--font-mono)", fontWeight: 600 }}>{p.drift_checks}</div></div>
                <div><div style={{ fontSize: 10.5, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>Exports</div><div style={{ fontSize: 15, fontFamily: "var(--font-mono)", fontWeight: 600 }}>{p.exports.toLocaleString()}</div></div>
              </div>

              <LangBar languages={p.languages} />
              <div style={{ marginTop: 8 }}>
                {Object.entries(p.languages).slice(0, 4).map(([l, n]) => (
                  <span key={l} className="language-chip" style={{ "--_c": langColor(l) }}>{l} {Math.round(n/p.files*100)}%</span>
                ))}
              </div>

              <div style={{ marginTop: 12, display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--ink-3)", fontFamily: "var(--font-mono)" }}>
                <span>indexed {p.last_indexed}</span>
                {p.missing_files && <span style={{ color: "var(--warning)" }}>{p.missing_files} missing on disk</span>}
              </div>
            </div>
          </div>
        ))}
      </div>

      {MOCK.projects.length > pg.pageSize && (
        <div className="card" style={{ marginTop: 12 }}>
          <Pagination {...pg} label="projects" pageSizes={[6, 12, 24]} />
        </div>
      )}

      {selected && (
        <Drawer title={selected.name} onClose={() => setSelected(null)} footer={
          <>
            <button className="btn btn-danger"><Icon name="trash" size={13}/> Delete index</button>
            <div style={{ flex: 1 }} />
            <button className="btn btn-ghost" onClick={() => setSelected(null)}>Close</button>
            <button className="btn btn-accent"><Icon name="refresh" size={13}/> Re-index</button>
          </>
        }>
          <dl style={{ margin: 0, marginBottom: 20 }}>
            <div className="key-value"><dt>path</dt><dd>{selected.path}</dd></div>
            <div className="key-value"><dt>files</dt><dd>{selected.files.toLocaleString()}</dd></div>
            <div className="key-value"><dt>exports</dt><dd>{selected.exports.toLocaleString()}</dd></div>
            <div className="key-value"><dt>last_indexed</dt><dd>{selected.last_indexed}</dd></div>
            <div className="key-value"><dt>status</dt><dd>{selected.stale ? <span className="badge badge-warning">stale</span> : <span className="badge badge-success">healthy</span>}</dd></div>
            {selected.missing_files && <div className="key-value"><dt>missing_on_disk</dt><dd style={{ color: "var(--warning)" }}>{selected.missing_files}</dd></div>}
          </dl>
          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "0 0 10px" }}>Language breakdown</h4>
          <LangBar languages={selected.languages} />
          <div style={{ marginTop: 12 }}>
            {Object.entries(selected.languages).map(([l, n]) => (
              <div key={l} style={{ display: "flex", justifyContent: "space-between", padding: "5px 0", fontSize: 12.5, fontFamily: "var(--font-mono)", borderBottom: "1px dashed var(--border)" }}>
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: langColor(l) }} /> {l}
                </span>
                <span style={{ color: "var(--ink-3)" }}>{n} files · {Math.round(n/selected.files*100)}%</span>
              </div>
            ))}
          </div>
        </Drawer>
      )}
    </>
  );
};

/* ---- Drift page ---- */
const DriftPage = () => {
  const [selected, setSelected] = useState(null);
  const [filter, setFilter] = useState("all");
  const rows = MOCK.drift.filter(d => filter === "all" || d.verdict === filter);
  const pg = usePagination(rows, 10, filter);

  const aligned = MOCK.drift.filter(d => d.verdict === "aligned").length;
  const minor = MOCK.drift.filter(d => d.verdict === "minor_drift").length;
  const major = MOCK.drift.filter(d => d.verdict === "significant_drift").length;
  const total = MOCK.drift.length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Drift</h1>
          <p className="page-desc">Cosine distance between task description and diff summary. Below 0.3 aligned, below 0.6 minor, above significant.</p>
        </div>
      </div>

      <div className="stat-grid" style={{ gridTemplateColumns: "repeat(4, 1fr)" }}>
        <div className="stat"><div className="stat-label">Total (30d)</div><div className="stat-value">{MOCK.summary.drift_checks_30d}</div></div>
        <div className="stat"><div className="stat-label" style={{ color: "var(--success)" }}>Aligned</div><div className="stat-value">{aligned}<span className="stat-unit">/{total}</span></div><div className="stat-delta">{Math.round(aligned/total*100)}% of recent</div></div>
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
                <td className="mono dim">{d.ts.split(" ")[1]}</td>
              </tr>
            ))}
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
  const rows = MOCK.sessions.filter(s => filter === "all" || s.status === filter);
  const pg = usePagination(rows, 10, filter);

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
                <td style={{ maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.original_request}</td>
                <td><StatusBadge s={s.status} /></td>
                <td><span className="badge">{s.task_classification}</span></td>
                <td className="mono">{s.project}</td>
                <td className="mono" style={{ textAlign: "right" }}>v{s.version}</td>
                <td className="mono dim">{s.created_at.split(" ")[1]}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <Pagination {...pg} label="sessions" />
      </div>

      {selected && (
        <Drawer title={selected.session_id} onClose={() => setSelected(null)} footer={
          <>
            {selected.status === "running" && <button className="btn btn-danger">Kill session</button>}
            <div style={{ flex: 1 }} />
            <button className="btn btn-secondary"><Icon name="copy" size={13} /> Copy ID</button>
            <button className="btn btn-accent">Resume</button>
          </>
        }>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
            <StatusBadge s={selected.status} />
            <span className="badge">{selected.task_classification}</span>
            <span className="badge">v{selected.version}</span>
            <TierBadge t={selected.state.model_tier} />
          </div>

          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "0 0 6px" }}>Original request</h4>
          <p style={{ margin: 0, fontSize: 13.5, fontWeight: 500 }}>{selected.original_request}</p>

          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 8px" }}>Progress</h4>
          <div>
            {selected.completed_steps.map(s => <span key={s} className="step-chip done"><Icon name="check" size={10}/> {s}</span>)}
            {selected.remaining_steps.map(s => <span key={s} className="step-chip pending">{s}</span>)}
          </div>

          {selected.decisions.length > 0 && <>
            <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>Decisions</h4>
            <ul style={{ margin: 0, paddingLeft: 18, fontSize: 13, lineHeight: 1.6 }}>
              {selected.decisions.map((d, i) => <li key={i}>{d}</li>)}
            </ul>
          </>}

          {selected.files_changed.length > 0 && <>
            <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>Files changed</h4>
            <div>
              {selected.files_changed.map(f => <div key={f} style={{ padding: "5px 10px", background: "var(--bg-sunken)", borderRadius: 4, fontFamily: "var(--font-mono)", fontSize: 12, marginBottom: 4 }}>{f}</div>)}
            </div>
          </>}

          {selected.errors.length > 0 && <>
            <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--danger)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>Errors</h4>
            {selected.errors.map((e, i) => <div key={i} style={{ padding: "8px 10px", background: "var(--danger-bg)", color: "var(--danger)", borderRadius: 4, fontSize: 12.5, marginBottom: 4 }}>{e}</div>)}
          </>}

          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>State snapshot</h4>
          <JsonView value={selected.state} />
        </Drawer>
      )}
    </>
  );
};

Object.assign(window, { ProjectsPage, DriftPage, SessionsPage });
