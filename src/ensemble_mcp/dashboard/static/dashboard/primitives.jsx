/* ensemble-mcp — icons and small primitives */

const { useState, useEffect, useRef, useMemo, useCallback } = React;

/* ---- Icons (outline, 1.5 stroke) ---- */
const Icon = ({ name, size = 16, className = "" }) => {
  const common = {
    width: size, height: size, viewBox: "0 0 24 24",
    fill: "none", stroke: "currentColor", strokeWidth: 1.5,
    strokeLinecap: "round", strokeLinejoin: "round",
    className,
  };
  const P = (d) => <svg {...common}><path d={d} /></svg>;
  switch (name) {
    case "home":     return P("M3 11l9-8 9 8M5 10v10h14V10");
    case "patterns": return P("M4 5h6v6H4zM14 5h6v6h-6zM4 15h6v6H4zM14 15h6v6h-6z");
    case "skills":   return P("M12 2l3 6 6 1-4.5 4 1 6-5.5-3-5.5 3 1-6L3 9l6-1z");
    case "projects": return P("M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2z");
    case "drift":    return P("M3 17l6-6 4 4 8-8M14 7h7v7");
    case "sessions": return P("M3 12a9 9 0 1018 0 9 9 0 00-18 0zM12 7v5l3 2");
    case "settings": return P("M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09a1.65 1.65 0 00-1-1.51 1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 110-4h.09a1.65 1.65 0 001.51-1 1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33h0a1.65 1.65 0 001-1.51V3a2 2 0 114 0v.09a1.65 1.65 0 001 1.51h0a1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82v0a1.65 1.65 0 001.51 1H21a2 2 0 110 4h-.09a1.65 1.65 0 00-1.51 1z");
    case "health":   return P("M3 12h4l3-9 4 18 3-9h4");
    case "search":   return P("M21 21l-4.3-4.3M11 18a7 7 0 110-14 7 7 0 010 14z");
    case "close":    return P("M6 6l12 12M18 6L6 18");
    case "edit":     return P("M4 20h4l10-10-4-4L4 16v4zM14 6l4 4");
    case "trash":    return P("M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13");
    case "refresh":  return P("M21 12a9 9 0 11-3-6.7L21 8M21 3v5h-5");
    case "copy":     return P("M8 4h10a2 2 0 012 2v10M6 8h10a2 2 0 012 2v10a2 2 0 01-2 2H6a2 2 0 01-2-2V10a2 2 0 012-2z");
    case "check":    return P("M5 12l5 5 9-11");
    case "x-small":  return P("M7 7l10 10M17 7L7 17");
    case "plus":     return P("M12 5v14M5 12h14");
    case "chevron-right": return P("M9 5l7 7-7 7");
    case "chevron-left":  return P("M15 5l-7 7 7 7");
    case "chevrons-right": return P("M7 5l7 7-7 7M13 5l7 7-7 7");
    case "chevrons-left":  return P("M17 5l-7 7 7 7M11 5l-7 7 7 7");
    case "chevron-down":  return P("M6 9l6 6 6-6");
    case "external": return P("M14 5h5v5M19 5l-9 9M5 7v12h12");
    case "filter":   return P("M4 5h16M7 12h10M10 19h4");
    case "more":     return P("M5 12h.01M12 12h.01M19 12h.01");
    case "sun":      return P("M12 4V2M12 22v-2M4 12H2M22 12h-2M6 6L4.5 4.5M19.5 19.5L18 18M6 18l-1.5 1.5M19.5 4.5L18 6M12 17a5 5 0 100-10 5 5 0 000 10z");
    case "moon":     return P("M21 13A9 9 0 1111 3a7 7 0 0010 10z");
    case "dot":      return <svg {...common}><circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" /></svg>;
    case "play":     return P("M7 4v16l13-8z");
    case "pause":    return P("M7 5v14M17 5v14");
    case "logo":     return (
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
        <rect x="3" y="3" width="7" height="7" rx="1.2" fill="currentColor" opacity=".9" />
        <rect x="14" y="3" width="7" height="7" rx="1.2" fill="currentColor" opacity=".55" />
        <rect x="3" y="14" width="7" height="7" rx="1.2" fill="currentColor" opacity=".55" />
        <rect x="14" y="14" width="7" height="7" rx="1.2" fill="currentColor" opacity=".9" />
      </svg>
    );
    case "arrow-up": return P("M12 19V5M5 12l7-7 7 7");
    case "database": return P("M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3v12c0 1.7-3.6 3-8 3s-8-1.3-8-3zM4 6c0 1.7 3.6 3 8 3s8-1.3 8-3M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3");
    case "cpu":      return P("M5 5h14v14H5zM9 9h6v6H9zM9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2");
    case "folder":   return P("M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2z");
    case "file":     return P("M14 3H6a2 2 0 00-2 2v14a2 2 0 002 2h12a2 2 0 002-2V9zM14 3v6h6");
    case "download": return P("M12 3v12M7 10l5 5 5-5M5 21h14");
    case "zap":      return P("M13 2L3 14h7l-1 8 11-12h-7z");
    case "bug-report": return P("M8 3l1 2h6l1-2M5 8a5 5 0 0114 0v6a7 7 0 01-14 0zM2 13h3M19 13h3M4 7l2 2M20 7l-2 2M12 13v6");
    default: return null;
  }
};

/* ---- Sparkline ---- */
const Sparkline = ({ data, width = 80, height = 28, color = "var(--accent)", fill = true }) => {
  if (!data || data.length < 2) return null;
  const max = Math.max(...data);
  const min = Math.min(...data);
  const range = max - min || 1;
  const step = width / (data.length - 1);
  const points = data.map((v, i) => [i * step, height - ((v - min) / range) * (height - 2) - 1]);
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
  const area = `${path} L${width},${height} L0,${height} Z`;
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      {fill && <path d={area} fill={color} opacity="0.12" />}
      <path d={path} fill="none" stroke={color} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
};

/* ---- Bar-chart (small) ---- */
const MiniBars = ({ data, width = 180, height = 48, color = "var(--accent)" }) => {
  if (!data) return null;
  const max = Math.max(...data, 1);
  const bw = width / data.length;
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      {data.map((v, i) => {
        const h = Math.max(2, (v / max) * (height - 4));
        return <rect key={i} x={i * bw + 1} y={height - h} width={bw - 2} height={h} fill={color} opacity={0.85} rx="1" />;
      })}
    </svg>
  );
};

/* ---- Badge helpers ---- */
const CategoryBadge = ({ cat }) => {
  const map = {
    "gotcha": "badge-warning",
    "problem-solution": "badge-accent",
    "how-it-works": "badge-info",
    "what-changed": "badge",
    "discovery": "badge-success",
    "decision": "badge",
    "trade-off": "badge",
    "general": "badge",
  };
  return <span className={`badge ${map[cat] || "badge"}`}>{cat}</span>;
};
const VerdictBadge = ({ v }) => {
  if (v === "aligned") return <span className="badge badge-success"><Icon name="check" size={10} /> aligned</span>;
  if (v === "minor_drift") return <span className="badge badge-warning">minor drift</span>;
  if (v === "significant_drift") return <span className="badge badge-danger">significant</span>;
  return <span className="badge">{v}</span>;
};
const StatusBadge = ({ s }) => {
  const m = {
    running: "badge-info", completed: "badge-success", failed: "badge-danger",
    killed: "badge-warning", pending: "badge",
  };
  return <span className={`badge ${m[s] || "badge"}`}>{s}</span>;
};
const TierBadge = ({ t }) => {
  const m = { best: "badge-accent", mid: "badge-info", cheapest: "badge" };
  return <span className={`badge ${m[t] || "badge"}`}>{t}</span>;
};

/* ---- LangBar (stacked file count) ---- */
const LangBar = ({ languages }) => {
  const entries = Object.entries(languages || {});
  const total = entries.reduce((s, [,n]) => s + n, 0) || 1;
  return (
    <div style={{ width: "100%", display: "flex", height: 4, borderRadius: 2, overflow: "hidden", background: "var(--bg-sunken)" }}>
      {entries.map(([lang, n]) => (
        <div key={lang} title={`${lang} · ${n}`} style={{ width: `${(n/total)*100}%`, background: langColor(lang) }} />
      ))}
    </div>
  );
};

/* ---- Fake JSON syntax highlighter ---- */
const JsonView = ({ value }) => {
  const json = JSON.stringify(value, null, 2);
  const highlighted = json.replace(
    /("[^"]+"\s*:)|(\b\d+(\.\d+)?\b)|("[^"]*")|\b(true|false|null)\b/g,
    (m, k, n, _n2, s, b) => {
      if (k) return `<span class="k">${k.replace(/:$/, "")}</span>:`;
      if (n) return `<span class="n">${n}</span>`;
      if (s) return `<span class="s">${s}</span>`;
      if (b) return `<span class="b">${b}</span>`;
      return m;
    }
  );
  return <pre className="json-view" dangerouslySetInnerHTML={{ __html: highlighted }} />;
};

/* ---- Drawer ---- */
const Drawer = ({ title, onClose, children, footer }) => {
  useEffect(() => {
    const h = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);
  return (
    <>
      <div className="drawer-scrim" onClick={onClose} />
      <aside className="drawer">
        <div className="drawer-head">
          <h3 className="drawer-title">{title}</h3>
          <button className="icon-btn" onClick={onClose}><Icon name="close" size={14} /></button>
        </div>
        <div className="drawer-body">{children}</div>
        {footer && <div className="drawer-foot">{footer}</div>}
      </aside>
    </>
  );
};

/* ---- Pagination ---- */
const usePagination = (items, initialSize = 10, key) => {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(initialSize);
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  // clamp page when filters shrink the set
  useEffect(() => { if (page > totalPages) setPage(1); }, [totalPages, page]);
  useEffect(() => { setPage(1); }, [key]);
  const start = (page - 1) * pageSize;
  const slice = items.slice(start, start + pageSize);
  return {
    slice, page, setPage, pageSize, setPageSize, total, totalPages,
    from: total === 0 ? 0 : start + 1,
    to: Math.min(start + pageSize, total),
  };
};

const Pagination = ({ page, setPage, totalPages, total, from, to, pageSize, setPageSize, pageSizes = [10, 25, 50], label = "rows" }) => {
  if (total === 0) {
    return (
      <div className="pagination">
        <span>No {label}</span>
      </div>
    );
  }
  // compact page list with ellipses
  const nums = [];
  const push = (n) => nums.push(n);
  const last = totalPages;
  if (last <= 7) {
    for (let i = 1; i <= last; i++) push(i);
  } else {
    push(1);
    if (page > 3) push("…");
    for (let i = Math.max(2, page - 1); i <= Math.min(last - 1, page + 1); i++) push(i);
    if (page < last - 2) push("…");
    push(last);
  }
  return (
    <div className="pagination">
      <span>
        Showing <b>{from}</b>–<b>{to}</b> of <b>{total}</b> {label}
      </span>
      <div className="pagination-controls">
        {setPageSize && (
          <select
            className="select pagination-size"
            value={pageSize}
            onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }}
            aria-label="rows per page"
          >
            {pageSizes.map(s => <option key={s} value={s}>{s} / page</option>)}
          </select>
        )}
        <button className="btn btn-sm btn-ghost" disabled={page === 1} onClick={() => setPage(1)} title="First">
          <Icon name="chevrons-left" size={13} />
        </button>
        <button className="btn btn-sm btn-ghost" disabled={page === 1} onClick={() => setPage(page - 1)} title="Previous">
          <Icon name="chevron-left" size={13} />
        </button>
        {nums.map((n, i) =>
          n === "…"
            ? <span key={`e${i}`} className="pagination-ellipsis">…</span>
            : <button key={n} className={`btn btn-sm ${n === page ? "btn-accent" : "btn-ghost"}`} onClick={() => setPage(n)}>{n}</button>
        )}
        <button className="btn btn-sm btn-ghost" disabled={page === totalPages} onClick={() => setPage(page + 1)} title="Next">
          <Icon name="chevron-right" size={13} />
        </button>
        <button className="btn btn-sm btn-ghost" disabled={page === totalPages} onClick={() => setPage(totalPages)} title="Last">
          <Icon name="chevrons-right" size={13} />
        </button>
      </div>
    </div>
  );
};

/* ---- Helpers ---- */
const fmtBytes = (b) => {
  if (b < 1024) return `${b} B`;
  if (b < 1024**2) return `${(b/1024).toFixed(1)} KB`;
  if (b < 1024**3) return `${(b/1024/1024).toFixed(1)} MB`;
  return `${(b/1024/1024/1024).toFixed(1)} GB`;
};
const fmtDuration = (ms) => ms < 1000 ? `${ms}ms` : `${(ms/1000).toFixed(2)}s`;
const fmtUptime = (s) => {
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return `${d}d ${h}h ${m}m`;
};

Object.assign(window, {
  Icon, Sparkline, MiniBars, CategoryBadge, VerdictBadge, StatusBadge, TierBadge,
  LangBar, JsonView, Drawer, Pagination, usePagination, fmtBytes, fmtDuration, fmtUptime,
  useState, useEffect, useRef, useMemo, useCallback,
});
