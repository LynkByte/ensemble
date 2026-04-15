# Design System Documentation: Kinetic Architect
 
## 1. Overview & Creative North Star
The design system for this AI Engineering platform is built upon the Creative North Star of **"The Kinetic Architect."** We are not building a generic dashboard; we are designing a high-performance cockpit for engineers who manipulate complex mental models. 
 
To achieve a "Linear-style" sophistication, we move away from the "template" look—characterized by rigid grids and 1px borders—and instead embrace **Intentional Asymmetry** and **Tonal Depth**. The interface should feel like a physical stack of semi-transparent architectural glass. We prioritize high information density without visual noise by using extreme typographic hierarchy and subtle tonal transitions.
 
## 2. Colors & Surface Philosophy
 
### The Palette
We utilize a deep, nocturnal foundation for the Dark Mode to reduce eye strain during deep work, and a crisp, editorial Light Mode for high-clarity review sessions.
 
*   **Primary (Electric Indigo):** `#a3a6ff` — Used for active states and critical path actions.
*   **Secondary (Mint Green):** `#69f6b8` — Used for secondary success metrics and "Go" states in code intelligence.
*   **Tertiary (Amber):** `#ffb148` — Reserved for drift warnings and warnings.
 
### The "No-Line" Rule
**Explicit Instruction:** Designers are prohibited from using 1px solid borders to define major sections (e.g., Sidebars, Headers, Main Content). 
*   Boundaries must be defined through background color shifts. 
*   Use `surface-container-low` (`#10131a`) sitting on `surface` (`#0b0e14`) to create a natural, "etched" look.
 
### Surface Hierarchy & Nesting
Treat the UI as a series of nested layers. Each tier of the `surface-container` scale adds a level of "elevation" or "focus."
*   **Level 0 (Background):** `surface` (`#0b0e14`). The void.
*   **Level 1 (Sidebar/Panels):** `surface-container-low` (`#10131a`).
*   **Level 2 (Cards/Main Workspace):** `surface-container` (`#161a21`).
*   **Level 3 (Modals/Popovers):** `surface-container-highest` (`#22262f`).
 
### The "Glass & Gradient" Rule
Main CTAs and high-level charts should utilize **Signature Textures**. Instead of a flat `#a3a6ff`, use a subtle linear gradient from `primary` to `primary-container` to add "soul." For floating elements (like the Cmd+K bar), apply **Glassmorphism**: `surface-variant` at 60% opacity with a `20px` backdrop-blur.
 
## 3. Typography
We use **Inter** for its technical precision. The goal is "Editorial Technicality"—high contrast between large, thin headlines and tiny, high-contrast labels.
 
*   **Display/Headline:** Use `headline-sm` (`1.5rem`) for page titles. Keep letter-spacing at `-0.02em` for a premium, tight look.
*   **Monospace Utility:** While the system uses Inter, code snippets and ID strings must use a high-fidelity mono font (e.g., SF Mono) to signify "Data."
*   **Labels:** Use `label-sm` (`0.6875rem`) with `0.05em` tracking for meta-data. This conveys an authoritative, "spec-sheet" aesthetic.
 
## 4. Elevation & Depth
 
### The Layering Principle
Depth is achieved by stacking tones. To make a card feel "lifted" off the `surface-container`, do not add a shadow immediately. First, try shifting the card's color to `surface-container-high`. 
 
### Ambient Shadows
When a floating effect is required (e.g., a "Prune Stale" dropdown), use **Ambient Shadows**:
*   **Shadow:** `0px 12px 32px rgba(0, 0, 0, 0.4)`
*   The shadow must be extra-diffused. For Light Mode, the shadow should be a tinted version of `inverse_on_surface` to mimic natural light.
 
### The "Ghost Border" Fallback
If a border is required for accessibility in high-density tables, it must be a **Ghost Border**:
*   Use `outline-variant` (`#45484f`) at **15% opacity**. 
*   It should be felt, not seen.
 
## 5. Components
 
### The "Command Center" (Cmd+K)
The search bar is the heart of the platform.
*   **Style:** Glassmorphic. `surface-container-highest` at 70% opacity.
*   **Border:** A Ghost Border (`outline-variant` @ 20%).
*   **Shadow:** Large ambient blur to separate it from the workspace.
 
### Buttons
*   **Primary:** A subtle gradient from `primary` to `primary_dim`. Corner radius: `md` (`0.375rem`).
*   **Secondary/Tertiary:** No background. Only `on_surface_variant` text that shifts to `primary` on hover.
*   **IconButton:** Monochrome by default. They only take on color (Electric Indigo) when active.
 
### Lists & Tables
*   **Row Hover:** Never use a border. Use a subtle background shift to `surface_bright` with a `200ms` ease-in-out transition.
*   **Status Indicators:** Use the "Pulsing Dot" pattern. A 6px circle using `secondary` (Mint) for "Healthy" or `error` (Pink-Red) for "Critical."
 
### Slim Sidebar
*   Width: `64px` collapsed, `240px` expanded.
*   Background: `surface-container-lowest` (`#000000`) to provide a strong vertical anchor against the `surface` background.
 
## 6. Do's and Don'ts
 
### Do
*   **DO** use whitespace to separate code intelligence modules instead of dividers.
*   **DO** use monochrome icons to maintain a professional, technical feel.
*   **DO** ensure that "Selected" states use the `primary` Indigo color as a high-contrast accent.
*   **DO** use `surface-container-low` for secondary content areas to create a "recessed" look.
 
### Don't
*   **DON'T** use 100% opaque, high-contrast white or grey borders.
*   **DON'T** use standard "Drop Shadows" with default settings; they look "cheap." Always use large, low-opacity ambient blurs.
*   **DON'T** use rounded corners larger than `xl` (`0.75rem`) for functional containers; keep it "Technical," not "Playful."
*   **DON'T** use colored icons for everything. Use color only to denote **State** (Success, Error, Warning).