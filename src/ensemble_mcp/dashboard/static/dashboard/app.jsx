/* ensemble-mcp — App shell (nav + tweaks + router) */

const NAV = [
  { id: "summary",  label: "Summary",  icon: "home" },
  { id: "patterns", label: "Patterns", icon: "patterns" },
  { id: "skills",   label: "Skills",   icon: "skills" },
  { id: "projects", label: "Projects", icon: "projects" },
  { id: "drift",    label: "Drift",    icon: "drift" },
  { id: "sessions", label: "Sessions", icon: "sessions" },
];
const NAV_BOTTOM = [
  { id: "bug-report", label: "Bug Report", icon: "bug-report" },
  { id: "settings",   label: "Settings",   icon: "settings" },
  { id: "health",     label: "Health",     icon: "health" },
];

const VALID_PAGES = new Set(["summary","patterns","skills","projects","drift","sessions","bug-report","settings","health"]);

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "light",
  "accent": "indigo",
  "density": "comfortable"
}/*EDITMODE-END*/;

const ACCENTS = {
  indigo:   { "--accent": "#6366F1", "--accent-600": "#4F46E5", "--accent-50": "#EEF2FF" },
  emerald:  { "--accent": "#10B981", "--accent-600": "#059669", "--accent-50": "#ECFDF5" },
  amber:    { "--accent": "#F59E0B", "--accent-600": "#D97706", "--accent-50": "#FEF3C7" },
  rose:     { "--accent": "#F43F5E", "--accent-600": "#E11D48", "--accent-50": "#FFE4E6" },
  slate:    { "--accent": "#475569", "--accent-600": "#334155", "--accent-50": "#F1F5F9" },
};

const App = () => {
  const [page, setPage] = useState(() => {
    const saved = localStorage.getItem("em_page");
    return saved && VALID_PAGES.has(saved) ? saved : "summary";
  });
  const [tweaks, setTweaks] = useState(TWEAK_DEFAULTS);
  const [tweaksOpen, setTweaksOpen] = useState(false);
  const [navData, setNavData] = useState(null);
  const [healthData, setHealthData] = useState(null);

  // Fetch nav counts from summary + health on mount and every 60s
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const [s, h] = await Promise.all([API.summary(), API.health()]);
        if (!cancelled) { setNavData(s); setHealthData(h); }
      } catch (e) { /* silent — nav counts just won't show */ }
    };
    load();
    const id = setInterval(load, 60000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  useEffect(() => { localStorage.setItem("em_page", page); }, [page]);

  useEffect(() => {
    document.documentElement.classList.toggle("theme-dark", tweaks.theme === "dark");
    const root = document.documentElement;
    const accent = ACCENTS[tweaks.accent] || ACCENTS.indigo;
    Object.entries(accent).forEach(([k, v]) => root.style.setProperty(k, v));
    root.style.setProperty("--density", tweaks.density === "compact" ? "0.85" : "1");
  }, [tweaks]);

  useEffect(() => {
    const onMsg = (e) => {
      if (e?.data?.type === "__activate_edit_mode") setTweaksOpen(true);
      if (e?.data?.type === "__deactivate_edit_mode") setTweaksOpen(false);
    };
    window.addEventListener("message", onMsg);
    window.parent.postMessage({ type: "__edit_mode_available" }, "*");
    return () => window.removeEventListener("message", onMsg);
  }, []);

  const setTweak = (k, v) => {
    const next = { ...tweaks, [k]: v };
    setTweaks(next);
    window.parent.postMessage({ type: "__edit_mode_set_keys", edits: { [k]: v } }, "*");
  };

  // Build nav items with live counts
  const navItems = NAV.map(n => {
    const item = { ...n };
    if (navData) {
      if (n.id === "patterns") item.count = navData.pattern_count;
      if (n.id === "skills")   { item.count = navData.active_skills; item.badge = navData.pending_skills || undefined; }
      if (n.id === "projects") item.count = navData.project_count;
      if (n.id === "drift")    item.count = navData.drift_checks_30d;
      if (n.id === "sessions") item.count = navData.session_count;
    }
    return item;
  });

  const pages = {
    summary: <SummaryPage onNavigate={setPage} />,
    patterns: <PatternsPage />,
    skills: <SkillsPage />,
    projects: <ProjectsPage />,
    drift: <DriftPage />,
    sessions: <SessionsPage />,
    "bug-report": <BugReportPage />,
    settings: <SettingsPage />,
    health: <HealthPage />,
  };

  const currentLabel = [...NAV, ...NAV_BOTTOM].find(n => n.id === page)?.label || "Summary";
  const version = healthData?.version || "…";
  const uptime = healthData?.uptime_seconds ?? null;

  return (
    <div className="app" data-screen-label={`ensemble-mcp · ${currentLabel}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Icon name="logo" size={16} /></div>
          <div className="brand-meta">
            <div className="brand-name">ensemble-mcp <span className="brand-version">v{version}</span></div>
            <div className="brand-sub">{window.location.host}</div>
          </div>
        </div>

        <nav className="nav">
          <div className="nav-label">Overview</div>
          {navItems.slice(0,1).map(n => (
            <div key={n.id} className={`nav-item ${page===n.id?"active":""}`} onClick={() => setPage(n.id)}>
              <Icon name={n.icon} className="nav-icon" /> {n.label}
            </div>
          ))}
          <div className="nav-label">Memory</div>
          {navItems.slice(1,3).map(n => (
            <div key={n.id} className={`nav-item ${page===n.id?"active":""}`} onClick={() => setPage(n.id)}>
              <Icon name={n.icon} className="nav-icon" /> {n.label}
              {n.badge ? <span className="nav-count"><span className="badge badge-accent" style={{ padding: "0px 5px", fontSize: 10 }}>{n.badge}</span></span>
                       : n.count ? <span className="nav-count">{n.count.toLocaleString()}</span> : null}
            </div>
          ))}
          <div className="nav-label">Pipeline</div>
          {navItems.slice(3).map(n => (
            <div key={n.id} className={`nav-item ${page===n.id?"active":""}`} onClick={() => setPage(n.id)}>
              <Icon name={n.icon} className="nav-icon" /> {n.label}
              {n.count ? <span className="nav-count">{n.count.toLocaleString()}</span> : null}
            </div>
          ))}
          <div className="nav-label">Server</div>
          {NAV_BOTTOM.map(n => (
            <div key={n.id} className={`nav-item ${page===n.id?"active":""}`} onClick={() => setPage(n.id)}>
              <Icon name={n.icon} className="nav-icon" /> {n.label}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className="status-dot" />
          <span>server online</span>
          <span className="sidebar-footer-meta">{uptime != null ? fmtUptime(uptime).split(" ").slice(0,2).join(" ") : "…"}</span>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            <span>ensemble-mcp</span>
            <span className="sep">/</span>
            <span className="current">{currentLabel.toLowerCase()}</span>
          </div>

          <div className="search">
            <Icon name="search" size={14} />
            <input placeholder="Search patterns, sessions, projects…" />
            <kbd>⌘K</kbd>
          </div>

          <div className="topbar-right">
            <span className="endpoint-chip"><span className="dot" /> {window.location.host}</span>
            <button className="icon-btn" title="Toggle theme" onClick={() => setTweak("theme", tweaks.theme === "dark" ? "light" : "dark")}>
              <Icon name={tweaks.theme === "dark" ? "sun" : "moon"} size={15} />
            </button>
            <button className="icon-btn" title="Refresh"><Icon name="refresh" size={15} /></button>
          </div>
        </header>

        <div className="content">
          {pages[page]}
        </div>
      </main>

      {tweaksOpen && (
        <div className="tweaks-panel">
          <div className="tweaks-head">
            Tweaks
            <button className="icon-btn" onClick={() => setTweaksOpen(false)}><Icon name="close" size={12} /></button>
          </div>
          <div className="tweaks-body">
            <div className="tweak-row">
              <div className="tweak-label">Theme</div>
              <div className="tweak-seg">
                {["light","dark"].map(t => (
                  <button key={t} className={tweaks.theme === t ? "active" : ""} onClick={() => setTweak("theme", t)}>{t}</button>
                ))}
              </div>
            </div>
            <div className="tweak-row">
              <div className="tweak-label">Accent</div>
              <div className="tweak-swatches">
                {Object.entries(ACCENTS).map(([name, colors]) => (
                  <div key={name}
                    className={`tweak-swatch ${tweaks.accent === name ? "active" : ""}`}
                    style={{ "--_c": colors["--accent"] }}
                    onClick={() => setTweak("accent", name)}
                    title={name}
                  />
                ))}
              </div>
            </div>
            <div className="tweak-row">
              <div className="tweak-label">Density</div>
              <div className="tweak-seg">
                {["comfortable","compact"].map(t => (
                  <button key={t} className={tweaks.density === t ? "active" : ""} onClick={() => setTweak("density", t)}>{t}</button>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
