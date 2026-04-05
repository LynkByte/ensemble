# Ensemble Design Specification

> Comprehensive system design for improving the Ensemble multi-agent orchestration system and building a companion Python MCP server.

**Status:** Design Complete, Implementation Pending  
**Version:** 1.0  
**Date:** 2026-03-30  
**Authors:** Collaborative design between user and AI assistant

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current System Analysis](#2-current-system-analysis)
3. [Improvement Priorities](#3-improvement-priorities)
4. [Split Design Documents](#4-split-design-documents)

---

## 1. Executive Summary

### Problem

The current 7-agent orchestration system works well but lacks:
- **Memory** — no learning from past pipelines; same mistakes repeat
- **Cost visibility** — no unified cross-tool token/cost tracking with confidence metadata
- **Drift detection** — agents can silently deviate from the plan
- **Smart routing** — model assignment is static, not task-aware
- **Extensibility** — no skills/hooks system for project-specific behavior
- **Skill intelligence** — no automatic detection of recurring patterns that should become reusable skills
- **Codebase indexing** — Scope re-explores from scratch every run, wasting tokens on repeat visits
- **User configuration** — models and reasoning are hardcoded; users must edit agent files to customize

### Solution

`ensemble-mcp` -- a Python MCP server providing vector memory, hybrid token/cost tracking (direct usage + parsers + estimation), drift detection, model routing, codebase indexing, and metrics. Distributed via `uvx` for zero-hassle cross-platform installation. Works with OpenCode, Claude Code, GitHub Copilot, Cursor, Windsurf, and Devin CLI.

### Goals

- Reduce token usage per pipeline by ~15-25% (up to ~40% on repeat visits with indexing)
- Provide per-agent cost visibility with accuracy indicators
- Enable cross-session learning (pattern memory)
- Support any project type (Laravel, Vue, Python, PHP, mobile, etc.)
- Let users customize models, reasoning, and budgets without editing agent files
- Zero-hassle installation: `uvx ensemble-mcp`

### System Overview

```mermaid
graph TB
    subgraph "ensemble-mcp Server"
        E[ensemble-mcp<br/>Python MCP Server]
        E --> F[Vector Memory<br/>ONNX + SQLite]
        E --> G[Token Tracking<br/>Direct Usage + Parsers + Estimation]
        E --> H[Drift Detection<br/>Cosine Similarity]
        E --> I[Model Routing<br/>Tier Recommendations]
        E --> J[Metrics & Reports<br/>Session Dashboard]
        E --> IDX[Codebase Index<br/>File Map + Exports + Imports]
        E --> SI[Skill Intelligence<br/>Pattern-to-Skill Graduation]
    end

    K[AI Tools] -->|MCP Protocol| E

    subgraph "Supported AI Tools"
        K1[OpenCode]
        K2[Claude Code]
        K3[GitHub Copilot]
        K4[Cursor]
        K5[Windsurf]
        K6[Devin CLI]
    end

    K1 & K2 & K3 & K4 & K5 & K6 --> K

    style E fill:#10B981,color:#fff
    style K fill:#F97316,color:#fff
    style IDX fill:#10B981,color:#fff
    style SI fill:#10B981,color:#fff
```

---

## 2. Current System Analysis

### File Inventory

| File | Lines | Role | Model | Temperature |
|------|-------|------|-------|-------------|
| `team-captain.md` | 250 | Primary orchestrator (Ensemble) | Global (Opus) | 0.3 |
| `team-architect.md` | 159 | Read-only planner (Scope) | Global (Opus) | 0.5 |
| `team-engineer.md` | 67 | Code writer (Craft) | Global (Opus) | 0.3 |
| `team-forge.md` | 134 | Format/build/test (Proof) | Sonnet 4.6 | 0.1 |
| `team-hunter.md` | 228 | Bug hunter (isolated, standalone) (Trace) | Global (Opus) | 0.2 |
| `team-inspector.md` | 142 | Code reviewer (Lens) | Sonnet 4.6 | 0.1 |
| `team-shipper.md` | 88 | Git operations (Signal) | GPT-5-mini | 0.1 |

**Total:** 1,068 lines across 7 agents

### Task Classification & Pipeline Shape

```mermaid
flowchart TD
    T[Incoming Task] --> Q1{Single-line<br/>change?}
    Q1 -->|Yes| TRIV["TRIVIAL<br/>Ensemble self-handles"]
    Q1 -->|No| Q2{Bug fix or<br/>isolated change?}
    Q2 -->|Yes| SIMP["SIMPLE<br/>4 steps: Plan → Implement → Build+Test → Git"]
    Q2 -->|No| Q3{Multi-file<br/>or new system?}
    Q3 -->|Multi-file| STD["STANDARD<br/>5 steps: Full pipeline"]
    Q3 -->|New system / major refactor| COMP["COMPLEX<br/>5 steps + Design Spec"]

    TRIV --> B1["Budget: 3 invocations"]
    SIMP --> B2["Budget: 6 invocations"]
    STD --> B3["Budget: 8 invocations"]
    COMP --> B4["Budget: 12 invocations"]

    style TRIV fill:#10B981,color:#fff
    style SIMP fill:#3B82F6,color:#fff
    style STD fill:#F59E0B,color:#000
    style COMP fill:#EF4444,color:#fff
```

### Strengths

- Clear separation of concerns — each agent has a well-defined role
- Context compression — Ensemble compresses each agent's output to 2-4 bullets
- Task classification — trivial/simple/standard/complex with pipeline shape adaptation
- Session persistence — `.opencode/resume.md` for resuming interrupted work
- Remediation loops — failing tests/reviews route back to Craft
- Pipeline budgets — per-classification invocation limits prevent runaway costs
- Model tiering — Opus for reasoning, Sonnet for execution, GPT-5-mini for Git
- Plan approval gate — user reviews the plan before implementation begins

### Weaknesses Found

1. **No pattern memory** — every pipeline starts from zero knowledge
2. **No token tracking** — no visibility into cost per agent or session
3. **No drift detection** — agents can drift from the plan without warning
4. **Static model routing** — model assignment doesn't adapt to task complexity
5. **No cross-tool skill discovery** — Craft, Proof, and Lens reference "skills" but each AI tool handles skill loading natively from its own locations (`.ai/skills/`, `.claude/skills/`, etc.); there's no unified way to discover skills across tools (MCP Phase 1 solves this with vector-based semantic search)
6. **Trace is isolated** — standalone agent at 228 lines, intentionally not part of the pipeline (invoked manually)
7. **No parallel execution** — Proof and Lens run sequentially but could overlap
8. **No hooks** — no extensibility points for project-specific behavior
9. **No `.gitignore`** — `.opencode/` directory not excluded from version control
10. **No codebase index** — Scope re-explores the project from scratch every pipeline run, wasting tokens on repeat visits
11. **No user configuration** — models, reasoning effort, and temperature are hardcoded in agent YAML frontmatter; users must edit agent files to customize
12. **No pattern-to-skill graduation** — recurring patterns in the pattern store are never automatically promoted to reusable skill files; users must manually notice repetition and create skills (Skill Intelligence feature addresses this)

### Permission Model

| Agent | Edit | Bash | Task | Webfetch |
|-------|------|------|------|----------|
| Ensemble | allow | allow | team-* only | - |
| Scope | deny | deny | - | allow |
| Craft | allow | allow | - | allow |
| Proof | allow | allow | - | allow |
| Trace | allow | allow | - | allow |
| Lens | deny | deny | - | allow |
| Signal | deny | git/gh/ls only | - | deny |

### Current Pipeline Flow

```mermaid
sequenceDiagram
    actor User
    participant Ens as Ensemble
    participant Sco as Scope
    participant Cra as Craft
    participant Pro as Proof
    participant Len as Lens
    participant Sig as Signal

    User->>Ens: Task request
    Ens->>Ens: Classify task

    rect rgb(59, 130, 246, 0.1)
        Note over Ens,Sco: Step 1: PLAN+EXPLORE
        Ens->>Sco: Analyze & plan
        Sco-->>Ens: Plan + file paths
    end

    Ens->>User: Present plan
    User->>Ens: Approve / Adjust / Reject

    rect rgb(16, 185, 129, 0.1)
        Note over Ens,Cra: Step 2: IMPLEMENT
        Ens->>Cra: Plan + context
        Cra-->>Ens: Files changed
    end

    rect rgb(249, 115, 22, 0.1)
        Note over Ens,Pro: Step 3: BUILD+TEST
        Ens->>Pro: Changed files
        Pro-->>Ens: Pass / Fail
    end

    rect rgb(245, 158, 11, 0.1)
        Note over Ens,Len: Step 4: REVIEW
        Ens->>Len: Changed files
        Len-->>Ens: Verdict
    end

    rect rgb(236, 72, 153, 0.1)
        Note over Ens,Sig: Step 5: GIT
        Ens->>Sig: Commit instructions
        Sig-->>Ens: Commit hash
    end

    Ens->>User: Pipeline report
```

---

## 3. Improvement Priorities

Ordered by impact-to-effort ratio:

| Priority | Feature | Impact | Effort |
|----------|---------|--------|--------|
| A | Session learning & pattern memory | High | Low -> Medium |
| B | Parallel execution (Proof + Lens) | Medium | Low |
| C | Anti-drift mechanisms | High | Low -> Medium |
| D | Smarter model routing | Medium | Medium |
| E | Skills/hooks system | Medium | Medium |
| F | User-configurable models & reasoning | High | Low |
| G | Codebase indexing | High | Medium |
| H | Skill Intelligence (auto-detect recurring patterns & stale skill removal) | Medium | Medium |

---

## 4. Split Design Documents

To keep this file concise, the detailed design sections were split into dedicated files:

- [MCP Server Design and Implementation Details](DESIGN-SPEC-PHASE-01.md)
- [Prompt-Level Improvements (Archival Reference)](referances/DESIGN-SPEC-PHASE-01.md)

Both files are canonical and should be used for implementation planning and execution.
