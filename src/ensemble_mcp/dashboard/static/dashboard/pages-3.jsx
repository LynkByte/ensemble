/* ensemble-mcp — Settings, Health pages */

const SettingsPage = () => {
  const [settings, setSettings] = useState(null);
  const [schema, setSchema] = useState(null);
  const [sourceMap, setSourceMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [dirty, setDirty] = useState({});
  const [saving, setSaving] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const [sData, schData] = await Promise.all([API.settings(), API.settingsSchema()]);
        if (cancelled) return;
        setSettings(sData.settings || {});
        setSourceMap(sData.source_map || {});
        setSchema(schData.schema || []);
      } catch (e) { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [refreshKey]);

  const sourceLabel = {
    default: "default",
    global_config: "~/.config",
    project_config: ".ensemble-mcp.toml",
    env: "ENV",
  };

  const handleChange = (key, value) => {
    setDirty(d => ({ ...d, [key]: value }));
  };

  const handleSave = async () => {
    if (Object.keys(dirty).length === 0) return;
    setSaving(true);
    try {
      // Convert string values to proper types based on schema
      const payload = {};
      for (const [key, val] of Object.entries(dirty)) {
        const field = schema?.find(f => f.name === key);
        if (field?.type === "integer") payload[key] = parseInt(val, 10);
        else if (field?.type === "float") payload[key] = parseFloat(val);
        else payload[key] = val;
      }
      await API.settingsUpdate(payload);
      setDirty({});
      setRefreshKey(k => k + 1);
    } catch (e) { alert(e.message); }
    finally { setSaving(false); }
  };

  const handleDiscard = () => setDirty({});

  const handleReset = async () => {
    if (!confirm("This will delete ALL data (patterns, sessions, projects, drift history, skills). Are you sure?")) return;
    try { await API.reset(); alert("All data has been reset."); setRefreshKey(k => k + 1); } catch (e) { alert(e.message); }
  };

  if (loading) return <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>Loading settings…</div>;

  // Group schema fields by a simple grouping heuristic
  const groups = {};
  const groupMap = {
    cache_dir: "Storage", db_path: "Storage", model_dir: "Storage",
    max_patterns: "Patterns", default_top_k: "Patterns", default_min_score: "Patterns", default_prune_max_age_days: "Patterns",
    drift_threshold_aligned: "Drift Detection", drift_threshold_minor: "Drift Detection",
    cluster_similarity_threshold: "Skills", default_min_cluster_size: "Skills", default_stale_threshold_days: "Skills",
    idempotency_key_ttl_hours: "Runtime",
  };
  (schema || []).forEach(f => {
    const group = groupMap[f.name] || "Other";
    (groups[group] ||= []).push(f);
  });

  const dirtyCount = Object.keys(dirty).length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-desc">Layered config — defaults → global → project → env. Changes write to <span className="tag">~/.config/ensemble-mcp/config.toml</span>.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-secondary" onClick={() => setRefreshKey(k => k + 1)}><Icon name="refresh" size={14}/> Reload</button>
          <button className="btn btn-ghost"><Icon name="download" size={14}/> Export TOML</button>
        </div>
      </div>

      <div className="card">
        <div className="card-head">
          <h3 className="card-title">Source legend</h3>
        </div>
        <div className="card-body" style={{ display: "flex", gap: 18, flexWrap: "wrap", fontSize: 12 }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span className="source-default" style={{ width: 8, height: 8, background: "var(--ink-4)", borderRadius: 2, display: "inline-block" }} /> default</span>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 8, height: 8, background: "var(--accent-600)", borderRadius: 2, display: "inline-block" }} /> global_config</span>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 8, height: 8, background: "var(--warning)", borderRadius: 2, display: "inline-block" }} /> project_config</span>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 8, height: 8, background: "var(--info)", borderRadius: 2, display: "inline-block" }} /> env variable</span>
          <div style={{ flex: 1 }} />
          <span style={{ color: "var(--ink-3)", fontFamily: "var(--font-mono)" }}>later layers override earlier</span>
        </div>
      </div>

      {Object.entries(groups).map(([name, items]) => (
        <div key={name} className="card" style={{ marginTop: 14 }}>
          <div className="card-head">
            <h3 className="card-title">{name}</h3>
            <span className="card-sub">{items.length} settings</span>
          </div>
          <div className="card-body">
            {items.map((f, i) => {
              const currentValue = dirty[f.name] !== undefined ? dirty[f.name] : (settings?.[f.name] ?? f.default ?? "");
              const source = sourceMap[f.name] || "default";
              return (
                <div key={f.name} className="setting-row" style={i > 0 ? { borderTop: "1px solid var(--border)" } : {}}>
                  <div className="setting-key">
                    <span>{f.name}</span>
                    <span className="setting-desc">{f.description}</span>
                    <span style={{ fontSize: 11, color: "var(--ink-4)", fontFamily: "var(--font-mono)" }}>
                      type: {f.type} · default: {String(f.default)}
                    </span>
                  </div>
                  <div>
                    {f.type === "integer" || f.type === "float" ? (
                      <input className="input mono" value={currentValue} type="number" step={f.type==="float" ? "0.01" : "1"}
                        onChange={e => handleChange(f.name, e.target.value)} />
                    ) : (
                      <input className="input mono" value={currentValue}
                        onChange={e => handleChange(f.name, e.target.value)} />
                    )}
                  </div>
                  <div className="setting-source">
                    <span className={`badge source-${source}`} style={{ background: "var(--bg-sunken)", borderColor: "transparent" }}>
                      {sourceLabel[source] || source}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      <div className="card" style={{ marginTop: 14, borderColor: "var(--danger-bg)" }}>
        <div className="card-head" style={{ borderColor: "var(--danger-bg)" }}>
          <h3 className="card-title" style={{ color: "var(--danger)" }}>Danger zone</h3>
        </div>
        <div className="card-body" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 500 }}>Reset all data</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>
              Deletes all patterns, sessions, project indexes, drift history, skill suggestions, and idempotency keys.
            </div>
          </div>
          <button className="btn btn-secondary" style={{ color: "var(--danger)", borderColor: "var(--danger-bg)" }} onClick={handleReset}>
            <Icon name="trash" size={13} /> Reset server…
          </button>
        </div>
      </div>

      <div style={{ position: "sticky", bottom: 0, marginTop: 18, padding: "12px 16px", background: "var(--bg-elev)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", display: "flex", alignItems: "center", justifyContent: "space-between", boxShadow: "var(--shadow-md)" }}>
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{dirtyCount} unsaved change{dirtyCount !== 1 ? "s" : ""}</span>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost" onClick={handleDiscard} disabled={dirtyCount === 0}>Discard</button>
          <button className="btn btn-accent" onClick={handleSave} disabled={dirtyCount === 0 || saving}>
            <Icon name="check" size={13}/> {saving ? "Saving…" : "Save to global config"}
          </button>
        </div>
      </div>
    </>
  );
};

/* ---- Health page ---- */
const HealthPage = () => {
  const [health, setHealth] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [h, s] = await Promise.all([API.health(), API.summary()]);
        if (!cancelled) { setHealth(h); setSummary(s); }
      } catch (e) { /* silent */ }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, []);

  if (loading) return <div style={{ padding: 40, textAlign: "center", color: "var(--ink-3)" }}>Loading health…</div>;
  if (!health) return <div style={{ padding: 40, textAlign: "center", color: "var(--danger)" }}>Failed to load health data</div>;

  const h = health;

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Health</h1>
          <p className="page-desc">Server status, database, and embedding model diagnostics.</p>
        </div>
      </div>

      <div className="health-grid">
        <div className="card">
          <div className="card-head"><h3 className="card-title"><Icon name="database" size={14}/> Database</h3></div>
          <div className="card-body">
            <dl style={{ margin: 0 }}>
              <div className="key-value"><dt>size</dt><dd>{fmtBytes(h.db_size_bytes)}</dd></div>
              <div className="key-value"><dt>patterns</dt><dd>{h.pattern_count ?? (summary?.pattern_count ?? "—")}</dd></div>
              <div className="key-value"><dt>sessions</dt><dd>{h.session_count ?? (summary?.session_count ?? "—")}</dd></div>
              <div className="key-value"><dt>projects</dt><dd>{h.project_count ?? (summary?.project_count ?? "—")}</dd></div>
              <div className="key-value"><dt>journal_mode</dt><dd>WAL</dd></div>
            </dl>
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h3 className="card-title"><Icon name="cpu" size={14}/> Embedding</h3></div>
          <div className="card-body">
            <dl style={{ margin: 0 }}>
              <div className="key-value"><dt>model</dt><dd>all-MiniLM-L6-v2</dd></div>
              <div className="key-value"><dt>dimensions</dt><dd>384</dd></div>
              <div className="key-value"><dt>runtime</dt><dd>ONNX Runtime</dd></div>
            </dl>
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h3 className="card-title"><Icon name="zap" size={14}/> Server</h3></div>
          <div className="card-body">
            <dl style={{ margin: 0 }}>
              <div className="key-value"><dt>status</dt><dd><span className="badge badge-success"><Icon name="check" size={10}/> {h.status}</span></dd></div>
              <div className="key-value"><dt>version</dt><dd>{h.version}</dd></div>
              <div className="key-value"><dt>name</dt><dd>{h.server_name}</dd></div>
              <div className="key-value"><dt>bind</dt><dd>127.0.0.1:8787</dd></div>
              <div className="key-value"><dt>auth</dt><dd><span className="badge">local only</span></dd></div>
            </dl>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-head">
          <h3 className="card-title">Available routes</h3>
          <span className="card-sub">read + mutation paths</span>
        </div>
        <table className="table">
          <thead><tr><th>Method</th><th>Path</th></tr></thead>
          <tbody>
            {[
              ["GET","/api/summary"],
              ["GET","/api/patterns"],
              ["GET","/api/skills"],
              ["GET","/api/projects"],
              ["GET","/api/drift"],
              ["GET","/api/sessions"],
              ["GET","/api/settings"],
              ["GET","/api/health"],
              ["GET","/api/reports/full"],
            ].map((r, i) => (
              <tr key={i}>
                <td className="mono" style={{ color: "var(--ink-3)" }}>{r[0]}</td>
                <td className="mono">{r[1]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
};

Object.assign(window, { SettingsPage, HealthPage });
