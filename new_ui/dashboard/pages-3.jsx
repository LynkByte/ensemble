/* ensemble-mcp — Settings, Health pages */

const SettingsPage = () => {
  const groups = {};
  MOCK.settings.forEach(s => {
    (groups[s.group] ||= []).push(s);
  });

  const sourceLabel = {
    default: "default",
    global_config: "~/.config",
    project_config: ".ensemble-mcp.toml",
    env: "ENV",
  };

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-desc">Layered config — defaults → global → project → env. Changes write to <span className="tag">~/.config/ensemble-mcp/config.toml</span>.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-secondary"><Icon name="refresh" size={14}/> Reload</button>
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
            {items.map((s, i) => (
              <div key={s.key} className="setting-row" style={i > 0 ? { borderTop: "1px solid var(--border)" } : {}}>
                <div className="setting-key">
                  <span>{s.key}</span>
                  <span className="setting-desc">{s.desc}</span>
                  <span style={{ fontSize: 11, color: "var(--ink-4)", fontFamily: "var(--font-mono)" }}>
                    type: {s.type} · default: {String(s.default)}
                  </span>
                </div>
                <div>
                  {s.type === "int" || s.type === "float" ? (
                    <input className="input mono" defaultValue={s.value} type="number" step={s.type==="float" ? "0.01" : "1"} />
                  ) : (
                    <input className="input mono" defaultValue={s.value} />
                  )}
                </div>
                <div className="setting-source">
                  <span className={`badge source-${s.source}`} style={{ background: "var(--bg-sunken)", borderColor: "transparent" }}>
                    {sourceLabel[s.source]}
                  </span>
                </div>
              </div>
            ))}
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
          <button className="btn btn-secondary" style={{ color: "var(--danger)", borderColor: "var(--danger-bg)" }}>
            <Icon name="trash" size={13} /> Reset server…
          </button>
        </div>
      </div>

      <div style={{ position: "sticky", bottom: 0, marginTop: 18, padding: "12px 16px", background: "var(--bg-elev)", border: "1px solid var(--border)", borderRadius: "var(--radius-lg)", display: "flex", alignItems: "center", justifyContent: "space-between", boxShadow: "var(--shadow-md)" }}>
        <span style={{ fontSize: 12, color: "var(--ink-3)" }}>2 unsaved changes</span>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost">Discard</button>
          <button className="btn btn-accent"><Icon name="check" size={13}/> Save to global config</button>
        </div>
      </div>
    </>
  );
};

/* ---- Health page ---- */
const HealthPage = () => {
  const h = MOCK.health;
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
              <div className="key-value"><dt>path</dt><dd>{h.db_path}</dd></div>
              <div className="key-value"><dt>size</dt><dd>{fmtBytes(h.db_size_bytes)}</dd></div>
              <div className="key-value"><dt>patterns</dt><dd>{MOCK.summary.pattern_count}</dd></div>
              <div className="key-value"><dt>sessions</dt><dd>{MOCK.summary.session_count}</dd></div>
              <div className="key-value"><dt>projects</dt><dd>{MOCK.summary.project_count}</dd></div>
              <div className="key-value"><dt>journal_mode</dt><dd>WAL</dd></div>
            </dl>
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h3 className="card-title"><Icon name="cpu" size={14}/> Embedding</h3></div>
          <div className="card-body">
            <dl style={{ margin: 0 }}>
              <div className="key-value"><dt>model</dt><dd>{h.embedding_model}</dd></div>
              <div className="key-value"><dt>dimensions</dt><dd>{h.embedding_dims}</dd></div>
              <div className="key-value"><dt>avg latency</dt><dd>{h.avg_embedding_ms} ms</dd></div>
              <div className="key-value"><dt>runtime</dt><dd>ONNX Runtime</dd></div>
              <div className="key-value"><dt>model_dir</dt><dd>{h.model_dir}</dd></div>
            </dl>
          </div>
        </div>

        <div className="card">
          <div className="card-head"><h3 className="card-title"><Icon name="zap" size={14}/> Server</h3></div>
          <div className="card-body">
            <dl style={{ margin: 0 }}>
              <div className="key-value"><dt>status</dt><dd><span className="badge badge-success"><Icon name="check" size={10}/> ok</span></dd></div>
              <div className="key-value"><dt>version</dt><dd>{h.version}</dd></div>
              <div className="key-value"><dt>name</dt><dd>{h.server_name}</dd></div>
              <div className="key-value"><dt>uptime</dt><dd>{fmtUptime(h.uptime_seconds)}</dd></div>
              <div className="key-value"><dt>bind</dt><dd>127.0.0.1:8787</dd></div>
              <div className="key-value"><dt>auth</dt><dd><span className="badge">local only</span></dd></div>
            </dl>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: 14 }}>
        <div className="card-head">
          <h3 className="card-title">Endpoint reachability</h3>
          <span className="card-sub">read + mutation paths</span>
        </div>
        <table className="table">
          <thead><tr><th>Method</th><th>Path</th><th>Status</th><th style={{ textAlign: "right" }}>p50</th><th style={{ textAlign: "right" }}>p95</th></tr></thead>
          <tbody>
            {[
              ["GET","/api/summary","ok",2,5],
              ["GET","/api/patterns","ok",4,12],
              ["GET","/api/skills","ok",3,8],
              ["GET","/api/projects","ok",5,14],
              ["GET","/api/drift","ok",4,9],
              ["GET","/api/sessions","ok",3,7],
              ["GET","/api/settings","ok",1,3],
              ["POST","/api/reset","ok","—","—"],
            ].map((r, i) => (
              <tr key={i}>
                <td className="mono" style={{ color: "var(--ink-3)" }}>{r[0]}</td>
                <td className="mono">{r[1]}</td>
                <td><span className="badge badge-success"><Icon name="check" size={10}/> {r[2]}</span></td>
                <td className="mono" style={{ textAlign: "right" }}>{r[3]}{typeof r[3] === "number" && "ms"}</td>
                <td className="mono" style={{ textAlign: "right" }}>{r[4]}{typeof r[4] === "number" && "ms"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
};

Object.assign(window, { SettingsPage, HealthPage });
