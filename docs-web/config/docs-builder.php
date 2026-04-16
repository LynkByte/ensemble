<?php

return [

    /*
    |--------------------------------------------------------------------------
    | Site Name
    |--------------------------------------------------------------------------
    */
    'site_name' => 'Ensemble',

    /*
    |--------------------------------------------------------------------------
    | Site Description
    |--------------------------------------------------------------------------
    */
    'site_description' => 'Multi-agent orchestration system for AI-powered software engineering workflows',

    /*
    |--------------------------------------------------------------------------
    | Source Directory
    |--------------------------------------------------------------------------
    | The directory where the Markdown documentation files are stored.
    */
    'source_dir' => base_path('/docs'),

    /*
    |--------------------------------------------------------------------------
    | Output Directory
    |--------------------------------------------------------------------------
    | The directory where the built HTML documentation will be written.
    */
    'output_dir' => public_path('docs'),

    /*
    |--------------------------------------------------------------------------
    | OpenAPI Spec File
    |--------------------------------------------------------------------------
    | Path to the OpenAPI YAML specification file used for generating
    | API reference pages.
    */
    'openapi_file' => null,

    /*
    |--------------------------------------------------------------------------
    | Base URL
    |--------------------------------------------------------------------------
    | The base URL path where the documentation will be served from.
    */
    'base_url' => '/docs',

    /*
    |--------------------------------------------------------------------------
    | Logo
    |--------------------------------------------------------------------------
    | Configure the logo displayed in the header. Set to null to use the
    | default diamond SVG, a string for inline SVG/HTML, or a URL path
    | to an image file.
    */
    'logo' => null,

    /*
    |--------------------------------------------------------------------------
    | Header Navigation
    |--------------------------------------------------------------------------
    | Links displayed in the top navigation bar. Each entry should have
    | a 'title' and 'url'. Set to null to use defaults (Guides, API
    | Reference, Examples).
    */
    'header_nav' => [
        ['title' => 'Documentation', 'url' => '/index.html'],
        ['title' => 'User Guide', 'url' => '/users/README.html'],
        ['title' => 'Design Specs', 'url' => '/DESIGN-SPEC.html'],
        ['title' => 'Future Plans', 'url' => '/FUTURE-PLANS.html'],
        ['title' => 'Business Case', 'url' => '/BUSINESS-CASE.html'],
        ['title' => 'Agent Reference', 'url' => '/references/README.html'],
    ],

    /*
    |--------------------------------------------------------------------------
    | Fonts
    |--------------------------------------------------------------------------
    | Google Font URLs to load. Set to false to disable external fonts.
    | Defaults to Inter + JetBrains Mono + Material Symbols.
    */
    'fonts' => [
        'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;900&family=JetBrains+Mono:wght@400;500;600&display=swap',
        'https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap',
    ],

    /*
    |--------------------------------------------------------------------------
    | Theme Name
    |--------------------------------------------------------------------------
    | The visual theme used for the documentation site.
    |
    | 'default' - The original DevDocs theme (blue, cool tones)
    | 'modern'  - A warm, polished theme inspired by Mintlify/Laravel docs
    |
    | Custom themes can be added by creating view and CSS/JS files under
    | resources/views/themes/{name}/ and resources/css/themes/{name}.css
    */
    'theme_name' => 'modern',

    /*
    |--------------------------------------------------------------------------
    | Asset Mode
    |--------------------------------------------------------------------------
    | How CSS/JS assets are handled during docs:build.
    |
    | 'precompiled' (default) - Uses pre-built assets from the package's
    |                           dist/ directory. Zero build step required.
    | 'vite'                  - Uses the host app's Vite build pipeline.
    |                           Requires docs CSS/JS as Vite entry points.
    */
    'asset_mode' => 'precompiled',

    /*
    |--------------------------------------------------------------------------
    | Theme Overrides
    |--------------------------------------------------------------------------
    | Override default CSS custom properties. These are injected as inline
    | <style> in the base layout. Set individual keys to override colors.
    |
    | Available keys: color-primary, color-primary-light, color-primary-dark,
    | and all --color-dark-* / --color-light-* / --color-code-* variables.
    */
    'theme' => [],

    /*
    |--------------------------------------------------------------------------
    | API Tag Icons
    |--------------------------------------------------------------------------
    | Map OpenAPI tags to Material Symbols icon names for sidebar display.
    | Extend or override the defaults. Any tag not listed here falls back
    | to 'api'.
    */
    'api_tag_icons' => [],

    /*
    |--------------------------------------------------------------------------
    | Navigation
    |--------------------------------------------------------------------------
    | Defines the sidebar navigation structure. Each section has a title
    | and an array of pages. Each page has a title, file (markdown source),
    | and an optional icon (Material Symbols name).
    |
    | Supported layouts: 'documentation' (default), 'api-reference'
    */
    'navigation' => [
        [
            'title' => 'Getting Started',
            'pages' => [
                ['title' => 'Home', 'file' => 'README.md', 'icon' => 'home'],
            ],
        ],
        [
            'title' => 'Design Specifications',
            'pages' => [
                ['title' => 'Overview', 'file' => 'DESIGN-SPEC.md', 'icon' => 'architecture'],
                ['title' => 'MCP Server', 'file' => 'DESIGN-SPEC-PHASE-01.md', 'icon' => 'dns'],
                ['title' => 'Prompt Improvements (Archival)', 'file' => 'references/DESIGN-SPEC-PHASE-01.md', 'icon' => 'edit_note'],
                ['title' => 'Future Plans', 'file' => 'FUTURE-PLANS.md', 'icon' => 'rocket'],
                ['title' => 'Business Case', 'file' => 'BUSINESS-CASE.md', 'icon' => 'trending_up'],
                ['title' => 'Test Scenarios', 'file' => 'EXAMPLE-SCENARIO.md', 'icon' => 'science'],
            ],
        ],
        [
            'title' => 'MCP Server',
            'pages' => [
                ['title' => 'Setup Guide', 'file' => 'SETUP.md', 'icon' => 'install_desktop'],
                ['title' => 'Architecture', 'file' => 'ARCHITECTURE.md', 'icon' => 'hub'],
                ['title' => 'API Reference', 'file' => 'API-REFERENCE.md', 'icon' => 'terminal'],
                ['title' => 'Contributing', 'file' => 'CONTRIBUTING.md', 'icon' => 'group'],
                ['title' => 'Dashboard Design', 'file' => 'DASHBOARD-DESIGN.md', 'icon' => 'dashboard'],
            ],
        ],
        [
            'title' => 'Releasing & Deployment',
            'pages' => [
                ['title' => 'Automated Release Workflow', 'file' => 'AUTOMATED-RELEASE.md', 'icon' => 'rocket_launch'],
                ['title' => 'Manual Release Process', 'file' => 'RELEASING.md', 'icon' => 'publish'],
            ],
        ],
        [
            'title' => 'User Guide',
            'pages' => [
                ['title' => 'Overview', 'file' => 'users/README.md', 'icon' => 'menu_book'],
                ['title' => 'Getting Started', 'file' => 'users/getting-started.md', 'icon' => 'play_circle'],
                ['title' => 'Installation', 'file' => 'users/installation.md', 'icon' => 'download'],
                ['title' => 'CLI Reference', 'file' => 'users/cli-reference.md', 'icon' => 'terminal'],
                ['title' => 'Configuration', 'file' => 'users/configuration.md', 'icon' => 'settings'],
                ['title' => 'MCP Clients', 'file' => 'users/mcp-clients.md', 'icon' => 'devices'],
                ['title' => 'Web Dashboard', 'file' => 'users/web-dashboard.md', 'icon' => 'dashboard'],
                ['title' => 'Tool Reference', 'file' => 'users/tool-reference.md', 'icon' => 'build'],
                ['title' => 'Integration Guide', 'file' => 'users/integration-guide.md', 'icon' => 'integration_instructions'],
                ['title' => 'Architecture Overview', 'file' => 'users/architecture-overview.md', 'icon' => 'hub'],
                ['title' => 'Troubleshooting', 'file' => 'users/troubleshooting.md', 'icon' => 'help'],
            ],
        ],
        [
            'title' => 'Agent Reference',
            'pages' => [
                ['title' => 'Pipeline Overview', 'file' => 'references/README.md', 'icon' => 'account_tree'],
                ['title' => 'Ensemble (Orchestrator)', 'file' => 'references/team-ensemble.md', 'icon' => 'star'],
                ['title' => 'Scope (Architect)', 'file' => 'references/team-scope.md', 'icon' => 'design_services'],
                ['title' => 'Craft (Engineer)', 'file' => 'references/team-craft.md', 'icon' => 'code'],
                ['title' => 'Forge (Build & Test)', 'file' => 'references/team-forge.md', 'icon' => 'construction'],
                ['title' => 'Lens (Review)', 'file' => 'references/team-lens.md', 'icon' => 'policy'],
                ['title' => 'Signal (Git Ops)', 'file' => 'references/team-signal.md', 'icon' => 'rocket_launch'],
                ['title' => 'Trace (Bug Detection)', 'file' => 'references/team-trace.md', 'icon' => 'bug_report'],
            ],
        ],
    ],

    /*
    |--------------------------------------------------------------------------
    | API Endpoint Navigation
    |--------------------------------------------------------------------------
    | Defines which OpenAPI tags/groups should appear in the API reference
    | sidebar and their display settings. Auto-generated from openapi.yaml
    | if left empty.
    */
    'api_navigation' => [],

    /*
    |--------------------------------------------------------------------------
    | Support URL
    |--------------------------------------------------------------------------
    | URL for the "Contact Support" link shown in the table of contents
    | sidebar. Set to null to hide the support card entirely.
    */
    'support_url' => null,

    /*
    |--------------------------------------------------------------------------
    | Footer
    |--------------------------------------------------------------------------
    */
    'footer' => [
        'copyright' => '© '.date('Y').' Ensemble by LynkByte. All rights reserved.',
        'links' => [],
    ],

];
