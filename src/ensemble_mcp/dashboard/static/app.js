/**
 * ensemble-mcp Dashboard — Alpine.js application
 *
 * Single-page app with client-side routing, API fetching, and Chart.js
 * visualizations for patterns, skills, projects, drift, and sessions.
 */

/* global Chart */

function dashboard() {
    return {
        // Navigation
        page: 'overview',
        pages: [
            { id: 'overview', label: 'Overview' },
            { id: 'patterns', label: 'Patterns' },
            { id: 'skills', label: 'Skills' },
            { id: 'projects', label: 'Projects' },
            { id: 'drift', label: 'Drift' },
            { id: 'sessions', label: 'Sessions' },
        ],

        // Global state
        version: '',
        loading: false,
        lastFetch: null,

        // Overview
        summary: {},

        // Patterns
        patterns: [],
        patternsTotal: 0,
        patternOffset: 0,
        patternFilter: '',
        expandedPattern: null,

        // Skills
        skillsTab: 'suggestions',
        skillSuggestions: [],
        skillTracked: [],
        staleSkills: [],

        // Projects
        projects: [],
        selectedProject: null,
        projectDetail: {},

        // Drift
        driftData: [],

        // Sessions
        sessions: [],
        sessionsTotal: 0,
        selectedSession: null,
        sessionDetail: {},

        // Charts
        _driftChart: null,
        _langChart: null,
        _roleChart: null,

        async init() {
            await this.loadHealth();
            await this.loadPage('overview');
        },

        async navigate(pageId) {
            this.page = pageId;
            // Reset detail views on navigation
            this.selectedProject = null;
            this.selectedSession = null;
            this.expandedPattern = null;
            await this.loadPage(pageId);
        },

        async loadPage(pageId) {
            switch (pageId) {
                case 'overview':
                    await Promise.all([this.loadSummary(), this.loadDrift()]);
                    this.$nextTick(() => this.renderDriftChart());
                    break;
                case 'patterns':
                    await this.loadPatterns();
                    break;
                case 'skills':
                    await Promise.all([this.loadSkills(), this.loadStaleSkills()]);
                    break;
                case 'projects':
                    await this.loadProjects();
                    break;
                case 'drift':
                    await this.loadDrift();
                    break;
                case 'sessions':
                    await this.loadSessions();
                    break;
            }
        },

        // ── API helpers ──────────────────────────────────────────

        async api(path) {
            this.loading = true;
            try {
                const res = await fetch(path);
                const json = await res.json();
                this.lastFetch = new Date();
                if (json.ok) {
                    return json.data;
                }
                console.error('API error:', json.error);
                return null;
            } catch (err) {
                console.error('Fetch error:', err);
                return null;
            } finally {
                this.loading = false;
            }
        },

        // ── Data loaders ─────────────────────────────────────────

        async loadHealth() {
            const data = await this.api('/api/health');
            if (data) {
                this.version = data.version || '';
            }
        },

        async loadSummary() {
            const data = await this.api('/api/summary');
            if (data) {
                this.summary = data;
            }
        },

        async loadPatterns() {
            const project = this.patternFilter ? `&project=${encodeURIComponent(this.patternFilter)}` : '';
            const data = await this.api(`/api/patterns?limit=50&offset=${this.patternOffset}${project}`);
            if (data) {
                this.patterns = data.patterns;
                this.patternsTotal = data.total;
            }
        },

        async loadSkills() {
            const data = await this.api('/api/skills');
            if (data) {
                this.skillSuggestions = data.suggestions;
                this.skillTracked = data.tracked;
            }
        },

        async loadStaleSkills() {
            const data = await this.api('/api/skills/stale');
            if (data) {
                this.staleSkills = data.stale_skills;
            }
        },

        async loadProjects() {
            const data = await this.api('/api/projects');
            if (data) {
                this.projects = data.projects;
            }
        },

        async loadProjectDetail(projectPath) {
            const data = await this.api(`/api/projects/${encodeURIComponent(projectPath)}`);
            if (data) {
                this.projectDetail = data;
                this.selectedProject = projectPath;
                this.$nextTick(() => {
                    this.renderLangChart();
                    this.renderRoleChart();
                });
            }
        },

        async loadDrift() {
            const data = await this.api('/api/drift?limit=100');
            if (data) {
                this.driftData = data.drift_checks;
            }
        },

        async loadSessions() {
            const data = await this.api('/api/sessions?limit=50');
            if (data) {
                this.sessions = data.sessions;
                this.sessionsTotal = data.total;
            }
        },

        async loadSessionDetail(sessionId) {
            const data = await this.api(`/api/sessions/${encodeURIComponent(sessionId)}`);
            if (data) {
                this.sessionDetail = data;
                this.selectedSession = sessionId;
            }
        },

        // ── Chart rendering ──────────────────────────────────────

        renderDriftChart() {
            if (this.driftData.length === 0) return;

            const canvas = document.getElementById('driftChart');
            if (!canvas) return;

            if (this._driftChart) {
                this._driftChart.destroy();
            }

            // Reverse to show chronological order (oldest first)
            const sorted = [...this.driftData].reverse();
            const labels = sorted.map(d => this.formatDateShort(d.created_at));
            const scores = sorted.map(d => d.score);

            this._driftChart = new Chart(canvas, {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label: 'Drift Score',
                        data: scores,
                        borderColor: '#F97316',
                        backgroundColor: 'rgba(249, 115, 22, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 3,
                        pointBackgroundColor: scores.map(s =>
                            s < 0.3 ? '#10B981' : s < 0.6 ? '#F59E0B' : '#EF4444'
                        ),
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        y: {
                            min: 0,
                            max: 1,
                            ticks: { color: '#9CA3AF' },
                            grid: { color: '#374151' },
                        },
                        x: {
                            ticks: { color: '#9CA3AF', maxTicksLimit: 15 },
                            grid: { color: '#374151' },
                        },
                    },
                    plugins: {
                        legend: { labels: { color: '#D1D5DB' } },
                    },
                },
            });
        },

        renderLangChart() {
            const canvas = document.getElementById('langChart');
            if (!canvas || !this.projectDetail.languages) return;

            if (this._langChart) {
                this._langChart.destroy();
            }

            const data = this.projectDetail.languages.slice(0, 10);
            const colors = [
                '#10B981', '#3B82F6', '#F97316', '#8B5CF6', '#EC4899',
                '#F59E0B', '#06B6D4', '#EF4444', '#84CC16', '#6366F1',
            ];

            this._langChart = new Chart(canvas, {
                type: 'doughnut',
                data: {
                    labels: data.map(l => l.language),
                    datasets: [{
                        data: data.map(l => l.count),
                        backgroundColor: colors.slice(0, data.length),
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'right',
                            labels: { color: '#D1D5DB', font: { size: 11 } },
                        },
                    },
                },
            });
        },

        renderRoleChart() {
            const canvas = document.getElementById('roleChart');
            if (!canvas || !this.projectDetail.roles) return;

            if (this._roleChart) {
                this._roleChart.destroy();
            }

            const data = this.projectDetail.roles.slice(0, 10);

            this._roleChart = new Chart(canvas, {
                type: 'bar',
                data: {
                    labels: data.map(r => r.role),
                    datasets: [{
                        label: 'Files',
                        data: data.map(r => r.count),
                        backgroundColor: '#3B82F6',
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    indexAxis: 'y',
                    scales: {
                        x: {
                            ticks: { color: '#9CA3AF' },
                            grid: { color: '#374151' },
                        },
                        y: {
                            ticks: { color: '#9CA3AF' },
                            grid: { display: false },
                        },
                    },
                    plugins: {
                        legend: { display: false },
                    },
                },
            });
        },

        // ── Formatting helpers ───────────────────────────────────

        formatDate(dateStr) {
            if (!dateStr) return '';
            try {
                const d = new Date(dateStr + 'Z'); // SQLite dates are UTC
                return d.toLocaleString();
            } catch {
                return dateStr;
            }
        },

        formatDateShort(dateStr) {
            if (!dateStr) return '';
            try {
                const d = new Date(dateStr + 'Z');
                return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
            } catch {
                return dateStr;
            }
        },

        timeAgo(date) {
            if (!date) return '';
            const seconds = Math.floor((new Date() - date) / 1000);
            if (seconds < 60) return 'just now';
            if (seconds < 3600) return Math.floor(seconds / 60) + 'm ago';
            if (seconds < 86400) return Math.floor(seconds / 3600) + 'h ago';
            return Math.floor(seconds / 86400) + 'd ago';
        },
    };
}
