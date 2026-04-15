/**
 * ensemble-mcp Dashboard — Alpine.js application
 *
 * Single-page app with client-side routing, API fetching, Chart.js
 * visualizations, and mutation operations for patterns, skills,
 * projects, settings, and data management.
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
            { id: 'reports', label: 'Reports' },
            { id: 'settings', label: 'Settings' },
        ],

        // Global state
        version: '',
        loading: false,
        lastFetch: null,

        // Toast notifications
        toasts: [],

        // Confirmation dialog
        confirmVisible: false,
        confirmTitle: '',
        confirmMessage: '',
        confirmCallback: null,

        // Overview
        summary: {},

        // Patterns
        patterns: [],
        patternsTotal: 0,
        patternOffset: 0,
        patternFilter: '',
        expandedPattern: null,
        editingPattern: null,
        editPatternData: {},
        pruneMaxAgeDays: 90,

        // Skills
        skillsTab: 'suggestions',
        skillSuggestions: [],
        skillTracked: [],
        staleSkills: [],

        // Projects
        projects: [],
        selectedProject: null,
        projectDetail: {},
        projectHealth: null,
        reindexingProject: null,

        // Drift
        driftData: [],

        // Sessions
        sessions: [],
        sessionsTotal: 0,
        selectedSession: null,
        sessionDetail: {},

        // Settings
        settingsData: {},
        settingsSourceMap: {},
        settingsSchema: [],
        settingsForm: {},
        settingsSaving: false,

        // Charts
        _driftChart: null,
        _langChart: null,
        _roleChart: null,
        _healthChart: null,

        // Reports
        reportMarkdown: '',
        reportHistory: [],
        reportSummary: {},
        reportLoading: false,

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
            this.editingPattern = null;
            this.projectHealth = null;
            await this.loadPage(pageId);
        },

        async loadPage(pageId) {
            switch (pageId) {
                case 'overview':
                    await Promise.all([this.loadSummary(), this.loadDrift(), this.loadReportSummary()]);
                    this.$nextTick(() => requestAnimationFrame(() => this.renderDriftChart()));
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
                case 'settings':
                    await Promise.all([this.loadSettings(), this.loadSettingsSchema()]);
                    break;
                case 'reports':
                    await Promise.all([
                        this.loadReportMarkdown(),
                        this.loadReportHistory(),
                        this.loadReportSummary(),
                    ]);
                    this.$nextTick(() => requestAnimationFrame(() => this.renderHealthChart()));
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

        async apiMutate(path, method, body) {
            this.loading = true;
            try {
                const res = await fetch(path, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: body ? JSON.stringify(body) : undefined,
                });
                const json = await res.json();
                this.lastFetch = new Date();
                if (json.ok) {
                    return { ok: true, data: json.data };
                }
                const errMsg = json.error ? json.error.message : 'Unknown error';
                this.showToast(errMsg, 'error');
                return { ok: false, error: json.error };
            } catch (err) {
                console.error('Mutation error:', err);
                this.showToast('Request failed: ' + err.message, 'error');
                return { ok: false, error: err.message };
            } finally {
                this.loading = false;
            }
        },

        // ── Toast notifications ──────────────────────────────────

        showToast(message, type = 'info') {
            const id = Date.now() + Math.random();
            this.toasts.push({ id, message, type });
            setTimeout(() => {
                this.toasts = this.toasts.filter(t => t.id !== id);
            }, 4000);
        },

        // ── Confirmation dialog ──────────────────────────────────

        showConfirm(title, message, callback) {
            this.confirmTitle = title;
            this.confirmMessage = message;
            this.confirmCallback = callback;
            this.confirmVisible = true;
        },

        async doConfirm() {
            this.confirmVisible = false;
            if (this.confirmCallback) {
                await this.confirmCallback();
                this.confirmCallback = null;
            }
        },

        cancelConfirm() {
            this.confirmVisible = false;
            this.confirmCallback = null;
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
                this.projectHealth = null;
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

        async loadSettings() {
            const data = await this.api('/api/settings');
            if (data) {
                this.settingsData = data.settings;
                this.settingsSourceMap = data.source_map;
                // Initialize form with current values
                this.settingsForm = { ...data.settings };
            }
        },

        async loadSettingsSchema() {
            const data = await this.api('/api/settings/schema');
            if (data) {
                this.settingsSchema = data.schema;
            }
        },

        async loadProjectHealth(projectPath) {
            const data = await this.api(`/api/projects/${encodeURIComponent(projectPath)}/health`);
            if (data) {
                this.projectHealth = data;
            }
        },

        // ── Report loaders ──────────────────────────────────────

        async loadReportMarkdown() {
            this.reportLoading = true;
            const data = await this.api('/api/reports/markdown');
            this.reportLoading = false;
            if (data) {
                this.reportMarkdown = data.markdown || '';
            } else {
                this.reportMarkdown = '';
            }
        },

        async loadReportHistory() {
            const data = await this.api('/api/reports/history');
            if (data) {
                this.reportHistory = data.history || [];
            } else {
                this.reportHistory = [];
            }
        },

        async loadReportSummary() {
            const data = await this.api('/api/reports/summary');
            if (data) {
                this.reportSummary = data;
            } else {
                this.reportSummary = {};
            }
        },

        get renderedMarkdown() {
            if (!this.reportMarkdown) return '';
            try {
                const raw = typeof marked !== 'undefined' ? marked.parse(this.reportMarkdown) : this.reportMarkdown;
                return typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(raw) : raw;
            } catch {
                return this.reportMarkdown;
            }
        },

        // ── Pattern mutations ────────────────────────────────────

        deletePattern(id) {
            this.showConfirm(
                'Delete Pattern',
                'Are you sure you want to delete this pattern? This action cannot be undone.',
                async () => {
                    const result = await this.apiMutate(`/api/patterns/${id}`, 'DELETE');
                    if (result.ok) {
                        this.showToast('Pattern deleted successfully', 'success');
                        this.expandedPattern = null;
                        this.editingPattern = null;
                        await this.loadPatterns();
                    }
                }
            );
        },

        startEditPattern(p) {
            this.editingPattern = p.id;
            this.editPatternData = {
                name: p.name,
                context: p.context,
                approach: p.approach,
                outcome: p.outcome,
            };
        },

        cancelEditPattern() {
            this.editingPattern = null;
            this.editPatternData = {};
        },

        async saveEditPattern(id) {
            const result = await this.apiMutate(`/api/patterns/${id}`, 'PUT', this.editPatternData);
            if (result.ok) {
                this.showToast('Pattern updated successfully', 'success');
                this.editingPattern = null;
                this.editPatternData = {};
                await this.loadPatterns();
            }
        },

        prunePatterns() {
            this.showConfirm(
                'Prune Stale Patterns',
                `This will delete patterns older than ${this.pruneMaxAgeDays} days with zero matches. Continue?`,
                async () => {
                    const result = await this.apiMutate('/api/patterns/prune', 'POST', {
                        max_age_days: parseInt(this.pruneMaxAgeDays),
                    });
                    if (result.ok) {
                        this.showToast(`Pruned ${result.data.pruned} patterns (${result.data.remaining} remaining)`, 'success');
                        await this.loadPatterns();
                    }
                }
            );
        },

        // ── Skill mutations ──────────────────────────────────────

        async handleSkillSuggestion(id, action) {
            if (action === 'accept') {
                this.showConfirm(
                    'Accept Skill Suggestion',
                    'This will generate a skill file from this suggestion. Continue?',
                    async () => {
                        const result = await this.apiMutate(`/api/skills/suggestions/${id}/action`, 'POST', { action });
                        if (result.ok) {
                            this.showToast(`Skill ${action}ed successfully`, 'success');
                            await this.loadSkills();
                        }
                    }
                );
            } else {
                const result = await this.apiMutate(`/api/skills/suggestions/${id}/action`, 'POST', { action });
                if (result.ok) {
                    this.showToast(`Skill suggestion ${action}ed`, 'success');
                    await this.loadSkills();
                }
            }
        },

        deleteTrackedSkill(id) {
            this.showConfirm(
                'Delete Tracked Skill',
                'Remove this skill from tracking? The skill file itself will not be deleted.',
                async () => {
                    const result = await this.apiMutate(`/api/skills/tracked/${id}`, 'DELETE');
                    if (result.ok) {
                        this.showToast('Tracked skill removed', 'success');
                        await Promise.all([this.loadSkills(), this.loadStaleSkills()]);
                    }
                }
            );
        },

        // ── Settings mutations ───────────────────────────────────

        async saveSettings() {
            this.settingsSaving = true;
            // Only send fields that differ from current settings
            const changed = {};
            for (const [key, value] of Object.entries(this.settingsForm)) {
                if (JSON.stringify(value) !== JSON.stringify(this.settingsData[key])) {
                    // Type coercion for numeric fields
                    const schema = this.settingsSchema.find(s => s.name === key);
                    if (schema && schema.type === 'integer') {
                        changed[key] = parseInt(value);
                    } else if (schema && schema.type === 'float') {
                        changed[key] = parseFloat(value);
                    } else {
                        changed[key] = value;
                    }
                }
            }

            if (Object.keys(changed).length === 0) {
                this.showToast('No changes to save', 'info');
                this.settingsSaving = false;
                return;
            }

            const result = await this.apiMutate('/api/settings', 'PUT', changed);
            this.settingsSaving = false;
            if (result.ok) {
                this.showToast('Settings saved successfully', 'success');
                await this.loadSettings();
            }
        },

        resetAllData() {
            this.showConfirm(
                'Reset All Data',
                'This will permanently delete ALL stored data including patterns, sessions, indexed projects, skill suggestions, and drift history. This action cannot be undone!',
                async () => {
                    const result = await this.apiMutate('/api/reset', 'POST', { confirm: true });
                    if (result.ok) {
                        this.showToast('All data has been reset', 'success');
                        await this.loadHealth();
                    }
                }
            );
        },

        // ── Project mutations ────────────────────────────────────

        reindexProject(projectPath) {
            this.showConfirm(
                'Re-index Project',
                `Force re-index "${projectPath}"? This will clear and rebuild the entire index.`,
                async () => {
                    this.reindexingProject = projectPath;
                    const result = await this.apiMutate(
                        `/api/projects/${encodeURIComponent(projectPath)}/reindex`,
                        'POST'
                    );
                    this.reindexingProject = null;
                    if (result.ok) {
                        this.showToast(`Re-indexed ${result.data.files} files`, 'success');
                        await this.loadProjects();
                        if (this.selectedProject === projectPath) {
                            await this.loadProjectDetail(projectPath);
                        }
                    }
                }
            );
        },

        clearProjectIndex(projectPath) {
            this.showConfirm(
                'Clear Project Index',
                `Remove all indexed data for "${projectPath}"? The project can be re-indexed later.`,
                async () => {
                    const result = await this.apiMutate(
                        `/api/projects/${encodeURIComponent(projectPath)}`,
                        'DELETE'
                    );
                    if (result.ok) {
                        this.showToast('Project index cleared', 'success');
                        this.selectedProject = null;
                        await this.loadProjects();
                    }
                }
            );
        },

        // ── Chart rendering ──────────────────────────────────────

        renderDriftChart() {
            if (this.driftData.length === 0) return;

            const canvas = document.getElementById('driftChart');
            if (!canvas) return;

            const ctx = canvas.getContext('2d');
            if (!ctx || canvas.clientWidth === 0 || canvas.clientHeight === 0) return;

            if (this._driftChart) {
                this._driftChart.destroy();
                this._driftChart = null;
            }

            // Reverse to show chronological order (oldest first)
            const sorted = [...this.driftData].reverse();
            const labels = sorted.map(d => this.formatDateShort(d.created_at));
            const scores = sorted.map(d => d.score);

            try {
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
                        animation: false,
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
            } catch (e) {
                console.warn('Failed to render drift chart:', e);
            }
        },

        renderLangChart() {
            const canvas = document.getElementById('langChart');
            if (!canvas || !this.projectDetail.languages) return;

            const ctx = canvas.getContext('2d');
            if (!ctx || canvas.clientWidth === 0 || canvas.clientHeight === 0) return;

            if (this._langChart) {
                this._langChart.destroy();
                this._langChart = null;
            }

            const data = this.projectDetail.languages.slice(0, 10);
            const colors = [
                '#10B981', '#3B82F6', '#F97316', '#8B5CF6', '#EC4899',
                '#F59E0B', '#06B6D4', '#EF4444', '#84CC16', '#6366F1',
            ];

            try {
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
                        animation: false,
                        plugins: {
                            legend: {
                                position: 'right',
                                labels: { color: '#D1D5DB', font: { size: 11 } },
                            },
                        },
                    },
                });
            } catch (e) {
                console.warn('Failed to render language chart:', e);
            }
        },

        renderRoleChart() {
            const canvas = document.getElementById('roleChart');
            if (!canvas || !this.projectDetail.roles) return;

            const ctx = canvas.getContext('2d');
            if (!ctx || canvas.clientWidth === 0 || canvas.clientHeight === 0) return;

            if (this._roleChart) {
                this._roleChart.destroy();
                this._roleChart = null;
            }

            const data = this.projectDetail.roles.slice(0, 10);

            try {
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
                        animation: false,
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
            } catch (e) {
                console.warn('Failed to render role chart:', e);
            }
        },

        renderHealthChart() {
            if (this.reportHistory.length === 0) return;

            const canvas = document.getElementById('healthChart');
            if (!canvas) return;

            const ctx = canvas.getContext('2d');
            if (!ctx || canvas.clientWidth === 0 || canvas.clientHeight === 0) return;

            if (this._healthChart) {
                this._healthChart.destroy();
                this._healthChart = null;
            }

            const labels = this.reportHistory.map(h => {
                const d = new Date(h.date);
                return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
            });

            try {
                this._healthChart = new Chart(canvas, {
                    type: 'line',
                    data: {
                        labels,
                        datasets: [
                            {
                                label: 'Health Score',
                                data: this.reportHistory.map(h => h.health),
                                borderColor: '#10B981',
                                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                                fill: true,
                                tension: 0.3,
                                pointRadius: 4,
                                yAxisID: 'y',
                            },
                            {
                                label: 'Bugs',
                                data: this.reportHistory.map(h => h.bugs),
                                borderColor: '#EF4444',
                                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                                fill: false,
                                tension: 0.3,
                                pointRadius: 4,
                                yAxisID: 'y1',
                            },
                            {
                                label: 'Tests Passed',
                                data: this.reportHistory.map(h => h.tests_passed),
                                borderColor: '#3B82F6',
                                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                                fill: false,
                                tension: 0.3,
                                pointRadius: 4,
                                yAxisID: 'y1',
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: false,
                        interaction: {
                            mode: 'index',
                            intersect: false,
                        },
                        scales: {
                            y: {
                                type: 'linear',
                                position: 'left',
                                min: 0,
                                max: 100,
                                title: {
                                    display: true,
                                    text: 'Health Score',
                                    color: '#9CA3AF',
                                },
                                ticks: { color: '#9CA3AF' },
                                grid: { color: '#374151' },
                            },
                            y1: {
                                type: 'linear',
                                position: 'right',
                                min: 0,
                                title: {
                                    display: true,
                                    text: 'Count',
                                    color: '#9CA3AF',
                                },
                                ticks: { color: '#9CA3AF' },
                                grid: { drawOnChartArea: false },
                            },
                            x: {
                                ticks: { color: '#9CA3AF', maxTicksLimit: 10 },
                                grid: { color: '#374151' },
                            },
                        },
                        plugins: {
                            legend: { labels: { color: '#D1D5DB' } },
                        },
                    },
                });
            } catch (e) {
                console.warn('Failed to render health chart:', e);
            }
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
