/* ensemble-mcp — Bug Report page (Bug Hunter agent) */

const BUG_REPORT = {
  generated_at: "2026-04-22 10:42:18",
  project: "acme/api",
  commit: "a3f4d21",
  branch: "main",
  agent: "bug-hunter",
  agent_version: "1.4.0",
  duration_sec: 128,

  summary: {
    total_bugs: 12,
    code_smells: 28,
    health_score: 78,
    rating: "Moderate",
    ci_status: "PASS",
    trend: "Improving",
  },

  trend: {
    previous_score: 74,
    current_score: 78,
    change: +4,
    direction: "improving",
    history: [
      { date: "2026-03-24", health: 68, bugs: 19, smells: 42, critical: 2 },
      { date: "2026-03-31", health: 71, bugs: 17, smells: 38, critical: 1 },
      { date: "2026-04-07", health: 72, bugs: 16, smells: 34, critical: 1 },
      { date: "2026-04-14", health: 74, bugs: 14, smells: 32, critical: 0 },
      { date: "2026-04-22", health: 78, bugs: 12, smells: 28, critical: 0 },
    ],
  },

  health_breakdown: [
    { pillar: "Readability",       score: 17, max: 20, note: "Good naming; long functions in auth/middleware.py" },
    { pillar: "Maintainability",   score: 15, max: 20, note: "High cyclomatic complexity in orders_service.py" },
    { pillar: "Test Coverage",     score: 14, max: 20, note: "74% line coverage — gaps in error paths" },
    { pillar: "Modularity",        score: 16, max: 20, note: "2 circular import suspects in auth/*" },
    { pillar: "Dependency Health", score: 16, max: 20, note: "3 outdated packages, 0 known CVEs" },
  ],

  bugs: [
    { id: "BH-0412", title: "SQL injection risk via string-formatted ORDER BY",
      severity: "Critical", cvss: 9.2, category: "security",
      impact: 4, exploitability: 3, scope: 2, confidence: 1,
      location: "api/orders.py:142",
      fix: "Use SQLAlchemy text() binding or a whitelist for sort columns. Never interpolate user input into ORDER BY." },
    { id: "BH-0411", title: "N+1 query loading order.line_items in list endpoint",
      severity: "High", cvss: 7.4, category: "performance",
      impact: 3, exploitability: 2, scope: 2, confidence: 1,
      location: "api/orders.py:87",
      fix: "Eager-load with joinedload(Order.line_items) or batch via selectinload." },
    { id: "BH-0410", title: "JWT 'exp' claim not validated on refresh endpoint",
      severity: "High", cvss: 7.8, category: "security",
      impact: 3, exploitability: 3, scope: 1, confidence: 1,
      location: "auth/refresh.py:44",
      fix: "Pass verify_exp=True to jwt.decode and reject tokens > 30d old." },
    { id: "BH-0409", title: "Race condition on idempotency_key write (SQLite)",
      severity: "Medium", cvss: 6.1, category: "logic",
      impact: 2, exploitability: 2, scope: 1, confidence: 1,
      location: "api/idempotency.py:28",
      fix: "Wrap key lookup + insert in BEGIN IMMEDIATE transaction or use INSERT OR IGNORE semantics." },
    { id: "BH-0408", title: "Unbounded CSV import loaded into memory",
      severity: "Medium", cvss: 5.6, category: "performance",
      impact: 2, exploitability: 1, scope: 2, confidence: 1,
      location: "api/imports/csv.py:62",
      fix: "Stream with csv.DictReader over a file handle; chunk inserts." },
    { id: "BH-0407", title: "Inconsistent timezone handling (naive vs aware datetimes)",
      severity: "Medium", cvss: 4.9, category: "logic",
      impact: 2, exploitability: 1, scope: 1, confidence: 1,
      location: "models/order.py:18",
      fix: "Store UTC aware datetimes everywhere; convert at the edges." },
    { id: "BH-0406", title: "Missing error envelope in 2 MCP tool responses",
      severity: "Medium", cvss: 4.2, category: "contract",
      impact: 1, exploitability: 1, scope: 2, confidence: 1,
      location: "tools/session_save.py:102",
      fix: "Wrap error return in the standard {ok,data,error,meta} envelope." },
    { id: "BH-0405", title: "Broad except Exception swallows specific errors",
      severity: "Low", cvss: 3.1, category: "reliability",
      impact: 1, exploitability: 0, scope: 1, confidence: 1,
      location: "workers/dispatcher.py:58",
      fix: "Narrow to (ConnectionError, TimeoutError) and log the original exception." },
    { id: "BH-0404", title: "Deprecated pkg_resources still imported",
      severity: "Low", cvss: 2.4, category: "dependencies",
      impact: 1, exploitability: 0, scope: 0, confidence: 1,
      location: "utils/version.py:4",
      fix: "Switch to importlib.metadata.version (Python 3.8+)." },
    { id: "BH-0403", title: "Hardcoded localhost URL in dev config",
      severity: "Low", cvss: 1.8, category: "config",
      impact: 0, exploitability: 0, scope: 1, confidence: 1,
      location: "config/dev.py:12",
      fix: "Read from ENV with sensible default." },
    { id: "BH-0402", title: "Missing index on orders.status + created_at composite",
      severity: "Low", cvss: 2.1, category: "performance",
      impact: 1, exploitability: 0, scope: 0, confidence: 1,
      location: "migrations/0038_orders.sql",
      fix: "Add CREATE INDEX idx_orders_status_created ON orders(status, created_at)." },
    { id: "BH-0401", title: "assert used for runtime validation",
      severity: "Low", cvss: 1.5, category: "reliability",
      impact: 0, exploitability: 1, scope: 0, confidence: 0,
      location: "api/auth.py:34",
      fix: "assert is stripped with -O. Raise ValueError explicitly." },
  ],

  smells: [
    { type: "Long function",       count: 6, location: "orders_service.py, auth/middleware.py (+4)",
      fix: "Extract helpers; target < 50 lines per function." },
    { type: "God class",           count: 2, location: "OrderManager, AuthService",
      fix: "Split along single-responsibility lines: pricing, persistence, lifecycle." },
    { type: "Duplicate code",      count: 5, location: "api/*.py — response-envelope boilerplate",
      fix: "Extract @envelope decorator." },
    { type: "Feature envy",        count: 3, location: "Order.calc_tax() reaches into Customer",
      fix: "Move method to Customer or introduce TaxContext." },
    { type: "Primitive obsession", count: 4, location: "str for amounts, status, tenant_id",
      fix: "Introduce Money, OrderStatus, TenantId value objects." },
    { type: "Magic numbers",       count: 8, location: "Scattered across workers/*, billing/*",
      fix: "Extract to named constants or config." },
  ],

  structure: {
    issues: [
      "auth/ has both web and worker logic — split by boundary",
      "tests/ mirrors source but missing for 3 modules",
      "utils/ is becoming a dumping ground (18 unrelated helpers)",
    ],
    suggestions: [
      "Move auth/worker.py → workers/auth/",
      "Break utils/ into utils/time, utils/strings, utils/http",
      "Add tests/e2e/ to cover the 3 uncovered modules",
    ],
  },

  architecture: {
    detected: "Layered (Controllers → Services → Repositories)",
    score: 72,
    recommended: "Hexagonal",
    rationale: "Adapters for SQL, Redis, and MCP are currently called directly from services — invert dependencies via ports to simplify testing and future swaps.",
    violations: [
      "orders_service.py imports sqlalchemy directly (should go through a repository)",
      "workers/dispatcher.py uses http.client for MCP calls instead of the MCP adapter",
    ],
  },

  refactor_plan: [
    { step: 1, title: "Extract response-envelope decorator", effort: "S", impact: "M",
      desc: "Replace 5 duplicate envelope-construction blocks with @envelope." },
    { step: 2, title: "Introduce OrderRepository port", effort: "M", impact: "H",
      desc: "Move SQLAlchemy calls out of orders_service.py. Enables unit testing without DB." },
    { step: 3, title: "Fix SQL-injection in ORDER BY", effort: "S", impact: "H",
      desc: "Whitelist allowed sort columns; covered by BH-0412." },
    { step: 4, title: "Split OrderManager into Pricing + Lifecycle + Persistence", effort: "L", impact: "H",
      desc: "Address god-class smell. Land behind feature flag." },
    { step: 5, title: "Consolidate datetime handling to UTC-aware", effort: "M", impact: "M",
      desc: "Add mypy rule; migrate naive datetimes in 8 files." },
    { step: 6, title: "Add composite index on orders(status, created_at)", effort: "XS", impact: "M",
      desc: "Ships with migration 0042." },
  ],

  tests: {
    passed: 284,
    failed: 3,
    skipped: 4,
    duration_sec: 42.8,
    coverage_line: 74.2,
    coverage_branch: 61.4,
    failures: [
      { name: "test_orders_pagination::test_cursor_roundtrip",  kind: "logic",    file: "tests/test_orders.py:102" },
      { name: "test_auth::test_jwt_refresh_exp_rejection",     kind: "security", file: "tests/test_auth.py:58" },
      { name: "test_workers::test_retry_backoff",              kind: "flaky",    file: "tests/test_workers.py:44" },
    ],
  },

  ci: {
    status: "PASS",
    checks: [
      { name: "Health ≥ 70",          ok: true,  value: "78" },
      { name: "Health drop ≤ 10",     ok: true,  value: "+4" },
      { name: "No critical bugs open", ok: false, value: "1 critical (BH-0412)" },
      { name: "Coverage ≥ 70%",       ok: true,  value: "74.2%" },
      { name: "No test failures",     ok: false, value: "3 failed" },
    ],
    verdict_note: "Gate passes on health + trend; 2 sub-checks failed as warnings (tracked, not blocking in current config).",
  },
};

const SEV_COLOR = {
  Critical: { bg: "var(--danger-bg)", fg: "var(--danger)" },
  High:     { bg: "var(--warning-bg)", fg: "var(--warning)" },
  Medium:   { bg: "var(--info-bg)", fg: "var(--info)" },
  Low:      { bg: "var(--bg-sunken)", fg: "var(--ink-3)" },
};

const BugReportPage = () => {
  const r = BUG_REPORT;
  const [sevFilter, setSevFilter] = useState("all");
  const [selected, setSelected] = useState(null);
  const [tab, setTab] = useState("bugs");

  const bugsByS = { Critical: 0, High: 0, Medium: 0, Low: 0 };
  r.bugs.forEach(b => bugsByS[b.severity]++);
  const filtered = r.bugs.filter(b => sevFilter === "all" || b.severity === sevFilter);
  const pg = usePagination(filtered, 8, sevFilter);

  const healthColor = r.summary.health_score >= 85 ? "var(--success)"
                    : r.summary.health_score >= 60 ? "var(--warning)"
                    : "var(--danger)";

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Bug Report</h1>
          <p className="page-desc">
            Latest Bug Hunter scan · <span className="tag">{r.project}</span> · <span className="tag">{r.branch}@{r.commit}</span> · {r.generated_at} · {r.duration_sec}s
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost"><Icon name="download" size={14}/> Markdown</button>
          <button className="btn btn-secondary"><Icon name="external" size={14}/> History</button>
          <button className="btn btn-primary"><Icon name="refresh" size={14}/> Re-scan</button>
        </div>
      </div>

      {/* Hero: health gauge + ci + severity breakdown */}
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: "240px 1fr 1fr", gap: 0 }}>
          {/* Gauge */}
          <div style={{ padding: 20, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
            <GaugeRing value={r.summary.health_score} color={healthColor} />
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--ink-3)", fontWeight: 600 }}>Code Health</div>
            <div style={{ fontSize: 13, color: healthColor, fontWeight: 600 }}>{r.summary.rating}</div>
            <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--success)" }}>
              <Icon name="arrow-up" size={11}/> +{r.trend.change} vs. last scan
            </div>
          </div>

          {/* Bug severity */}
          <div style={{ padding: 20, borderRight: "1px solid var(--border)" }}>
            <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--ink-3)", fontWeight: 600, marginBottom: 12 }}>
              Bugs by severity · {r.summary.total_bugs} total
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {["Critical","High","Medium","Low"].map(s => {
                const pct = Math.round((bugsByS[s]/r.summary.total_bugs)*100) || 0;
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

          {/* CI + quick stats */}
          <div style={{ padding: 20 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--ink-3)", fontWeight: 600 }}>CI Quality Gate</div>
              <span className={`badge ${r.ci.status === "PASS" ? "badge-success" : "badge-danger"}`} style={{ fontSize: 11 }}>
                {r.ci.status === "PASS" ? <><Icon name="check" size={10}/> PASS</> : "FAIL"}
              </span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {r.ci.checks.map(c => (
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
        </div>
      </div>

      {/* Trend + code smells summary strip */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        <div className="card">
          <div className="card-head">
            <h3 className="card-title">Historical trend · 5 runs</h3>
            <span className="card-sub">{r.trend.direction}</span>
          </div>
          <div className="card-body" style={{ padding: 16 }}>
            <TrendChart history={r.trend.history} />
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3 className="card-title">Health breakdown · {r.summary.health_score}/100</h3>
            <span className="card-sub">5 pillars</span>
          </div>
          <div className="card-body" style={{ padding: "12px 16px" }}>
            {r.health_breakdown.map(p => {
              const pct = (p.score/p.max)*100;
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
                  <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>{p.note}</div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="toolbar">
        {[
          ["bugs",        `Bugs · ${r.summary.total_bugs}`],
          ["smells",      `Code smells · ${r.summary.code_smells}`],
          ["structure",   "Structure"],
          ["architecture","Architecture"],
          ["refactor",    `Refactor plan · ${r.refactor_plan.length}`],
          ["tests",       `Tests · ${r.tests.passed}/${r.tests.passed+r.tests.failed}`],
        ].map(([k, l]) => (
          <button key={k} className={`filter-chip ${tab===k?"active":""}`} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>

      {tab === "bugs" && (
        <>
          <div style={{ display: "flex", gap: 6, marginBottom: 10, flexWrap: "wrap" }}>
            {["all","Critical","High","Medium","Low"].map(s => (
              <button key={s} className={`filter-chip ${sevFilter===s?"active":""}`} onClick={() => setSevFilter(s)}>{s}</button>
            ))}
          </div>
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
                  const c = SEV_COLOR[b.severity];
                  return (
                    <tr key={b.id} onClick={() => setSelected(b)}>
                      <td className="mono">{b.id}</td>
                      <td style={{ fontWeight: 500 }}>{b.title}</td>
                      <td>
                        <span className="badge" style={{ background: c.bg, color: c.fg, borderColor: "transparent" }}>{b.severity}</span>
                      </td>
                      <td className="mono" style={{ textAlign: "right" }}>
                        <span style={{ color: c.fg, fontWeight: 500 }}>{b.cvss.toFixed(1)}</span>
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
        </>
      )}

      {tab === "smells" && (
        <div className="card">
          <table className="table">
            <thead>
              <tr>
                <th>Type</th><th style={{ textAlign: "right" }}>Count</th>
                <th>Location</th><th>Suggested fix</th>
              </tr>
            </thead>
            <tbody>
              {r.smells.map(s => (
                <tr key={s.type}>
                  <td style={{ fontWeight: 500 }}>{s.type}</td>
                  <td className="mono" style={{ textAlign: "right" }}>{s.count}</td>
                  <td className="mono dim">{s.location}</td>
                  <td style={{ color: "var(--ink-2)" }}>{s.fix}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "structure" && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
          <div className="card">
            <div className="card-head"><h3 className="card-title">Issues</h3></div>
            <div className="card-body">
              {r.structure.issues.map((x, i) => (
                <div key={i} style={{ padding: "8px 10px", background: "var(--warning-bg)", color: "var(--warning)", borderRadius: 4, fontSize: 12.5, marginBottom: 6 }}>{x}</div>
              ))}
            </div>
          </div>
          <div className="card">
            <div className="card-head"><h3 className="card-title">Suggestions</h3></div>
            <div className="card-body">
              {r.structure.suggestions.map((x, i) => (
                <div key={i} style={{ padding: "8px 10px", background: "var(--success-bg)", color: "var(--success)", borderRadius: 4, fontSize: 12.5, marginBottom: 6 }}>{x}</div>
              ))}
            </div>
          </div>
        </div>
      )}

      {tab === "architecture" && (
        <div className="card">
          <div className="card-body">
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 18 }}>
              <div style={{ padding: 14, background: "var(--bg-sunken)", borderRadius: 8 }}>
                <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--ink-3)", fontWeight: 600, marginBottom: 6 }}>Detected</div>
                <div style={{ fontSize: 15, fontWeight: 600 }}>{r.architecture.detected}</div>
                <div style={{ marginTop: 6, fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--ink-3)" }}>fit score {r.architecture.score}/100</div>
              </div>
              <div style={{ padding: 14, background: "var(--accent-50)", borderRadius: 8 }}>
                <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--accent-600)", fontWeight: 600, marginBottom: 6 }}>Recommended</div>
                <div style={{ fontSize: 15, fontWeight: 600, color: "var(--accent-600)" }}>{r.architecture.recommended}</div>
              </div>
            </div>
            <p style={{ fontSize: 13, lineHeight: 1.6, margin: "0 0 14px", color: "var(--ink-2)" }}>{r.architecture.rationale}</p>
            <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "0 0 8px" }}>Violations</h4>
            {r.architecture.violations.map((v, i) => (
              <div key={i} style={{ padding: "8px 10px", background: "var(--danger-bg)", color: "var(--danger)", borderRadius: 4, fontFamily: "var(--font-mono)", fontSize: 12, marginBottom: 4 }}>{v}</div>
            ))}
          </div>
        </div>
      )}

      {tab === "refactor" && (
        <div className="card">
          <div>
            {r.refactor_plan.map(s => (
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
      )}

      {tab === "tests" && (
        <>
          <div className="stat-grid" style={{ gridTemplateColumns: "repeat(5, 1fr)" }}>
            <div className="stat"><div className="stat-label" style={{ color: "var(--success)" }}>Passed</div><div className="stat-value">{r.tests.passed}</div></div>
            <div className="stat"><div className="stat-label" style={{ color: "var(--danger)" }}>Failed</div><div className="stat-value">{r.tests.failed}</div></div>
            <div className="stat"><div className="stat-label">Skipped</div><div className="stat-value">{r.tests.skipped}</div></div>
            <div className="stat"><div className="stat-label">Line cov</div><div className="stat-value">{r.tests.coverage_line}<span className="stat-unit">%</span></div></div>
            <div className="stat"><div className="stat-label">Branch cov</div><div className="stat-value">{r.tests.coverage_branch}<span className="stat-unit">%</span></div></div>
          </div>
          <div className="card">
            <div className="card-head"><h3 className="card-title">Failures</h3><span className="card-sub">{r.tests.duration_sec}s total</span></div>
            <table className="table">
              <thead><tr><th>Test</th><th>Kind</th><th>Location</th></tr></thead>
              <tbody>
                {r.tests.failures.map(f => (
                  <tr key={f.name}>
                    <td className="mono" style={{ fontWeight: 500 }}>{f.name}</td>
                    <td><span className={`badge ${f.kind==="security"?"badge-danger":f.kind==="flaky"?"badge-warning":"badge-info"}`}>{f.kind}</span></td>
                    <td className="mono dim">{f.file}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {selected && (
        <Drawer title={`${selected.id} · ${selected.title}`} onClose={() => setSelected(null)} footer={
          <>
            <button className="btn btn-ghost">Dismiss</button>
            <div style={{ flex: 1 }} />
            <button className="btn btn-secondary"><Icon name="copy" size={13}/> Copy fix</button>
            <button className="btn btn-accent"><Icon name="external" size={13}/> Open file</button>
          </>
        }>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 16 }}>
            <span className="badge" style={{ background: SEV_COLOR[selected.severity].bg, color: SEV_COLOR[selected.severity].fg, borderColor: "transparent" }}>{selected.severity}</span>
            <span className="badge">CVSS {selected.cvss.toFixed(1)}</span>
            <span className="badge">{selected.category}</span>
          </div>
          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "0 0 6px" }}>Location</h4>
          <div style={{ padding: "8px 10px", background: "var(--bg-sunken)", borderRadius: 4, fontFamily: "var(--font-mono)", fontSize: 12 }}>{selected.location}</div>

          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>CVSS breakdown</h4>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
            {[["Impact", selected.impact, 4],["Exploit", selected.exploitability, 3],["Scope", selected.scope, 2],["Conf.", selected.confidence, 1]].map(([l, v, m]) => (
              <div key={l} style={{ padding: 10, background: "var(--bg-sunken)", borderRadius: 6 }}>
                <div style={{ fontSize: 10.5, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--ink-3)", fontWeight: 600 }}>{l}</div>
                <div style={{ fontSize: 18, fontFamily: "var(--font-mono)", fontWeight: 600, marginTop: 2 }}>{v}<span style={{ fontSize: 12, color: "var(--ink-4)" }}>/{m}</span></div>
              </div>
            ))}
          </div>

          <h4 style={{ fontSize: 11, textTransform: "uppercase", color: "var(--ink-3)", letterSpacing: "0.08em", margin: "20px 0 6px" }}>Suggested fix</h4>
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, padding: "12px 14px", background: "var(--success-bg)", color: "var(--success)", borderRadius: 6 }}>{selected.fix}</p>
        </Drawer>
      )}
    </>
  );
};

/* ---- Gauge ring ---- */
const GaugeRing = ({ value, color, size = 140 }) => {
  const r = 56;
  const circ = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(100, value));
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
          <div style={{ fontSize: 34, fontWeight: 600, letterSpacing: "-0.02em", fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>{value}</div>
          <div style={{ fontSize: 11, color: "var(--ink-4)", fontFamily: "var(--font-mono)", marginTop: 2 }}>/ 100</div>
        </div>
      </div>
    </div>
  );
};

/* ---- Trend chart ---- */
const TrendChart = ({ history }) => {
  const w = 480, h = 160, pad = 24;
  const xs = history.length;
  const scores = history.map(h => h.health);
  const bugs = history.map(h => h.bugs);
  const minY = 50, maxY = 100;
  const yScale = v => h - pad - ((v - minY) / (maxY - minY)) * (h - pad*2);
  const xScale = i => pad + (i / (xs - 1)) * (w - pad*2);
  const scorePath = scores.map((v, i) => `${i===0?"M":"L"}${xScale(i).toFixed(1)},${yScale(v).toFixed(1)}`).join(" ");
  const bugsYScale = v => h - pad - ((v - 10) / (22 - 10)) * (h - pad*2);
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
            {row.date.slice(5)}
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

Object.assign(window, { BugReportPage, BUG_REPORT, SEV_COLOR });
