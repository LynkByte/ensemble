# Bug Hunter Report — ViewPulse

**Date:** 2026-04-23  
**Codebase:** ViewPulse (YouTube Analytics SaaS with AI Insights)  
**Stack:** PHP 8.5, Laravel 13.2.0, Livewire 4.2.2, Pest 4.4.3, Tailwind CSS 4, Laravel AI SDK 0.3.2  
**Database:** MySQL (default connection)  
**Test Suite:** 848 passed, 0 failed (2081 assertions)

---

## Summary

| Metric | Value |
|---|---|
| **Total New Bugs** | 6 |
| **Code Smells** | 10 (8 open from previous, 2 new) |
| **Health Score** | 78 / 100 (Moderate) |
| **Critical Bugs** | 0 |
| **High Bugs** | 1 |
| **Medium Bugs** | 3 |
| **Low Bugs** | 2 |
| **N+1 Query Issues** | 1 (new) |
| **CI Status** | **PASS** (score >= 70, no critical bugs) |

---

## Trends

| Metric | Previous (03-29) | Current (04-23) | Change |
|---|---|---|---|
| Health Score | 76 | 78 | +2 ⬆ |
| Bug Count | 10 (all fixed) | 6 (new) | 6 new findings |
| Code Smells | 12 (10 open) | 10 open | 0 change |
| Critical Issues | 0 | 0 | 0 |
| Tests Passed | 813 | 848 | +35 ⬆ |
| **Trend** | | | **Improving** |

---

## Bugs

### BUG-11: Dashboard::generateAiSummary() — AiContext not cleared on exception

- **Severity:** HIGH (CVSS 7.0)
- **Impact:** 3 (context leak between requests, wrong user/channel context for subsequent AI calls) | **Exploitability:** 3 (any AI call failure triggers it) | **Scope:** 1
- **Location:** `app/Livewire/Dashboard.php:204-237`
- **Detail:** `AiContext::bind()` is called at line 204, and `AiContext::clear()` at line 209 — but line 209 is BEFORE the catch block. If the AI agent call at lines 206-207 throws, execution jumps to the catch at line 231, skipping `AiContext::clear()`. The `finally` block at line 235 only resets `$aiSummaryLoading`. This is the exact same pattern that was fixed in BUG-9 (TrafficSources). Other components like `ShortsExplorer`, `ContentCalendarGenerator`, `CompetitorComparison`, `SubscriberGrowth`, and `AudienceRetention` correctly use `try/finally` for `AiContext::clear()`.
- **Fix:** Move `AiContext::clear()` into the `finally` block, or wrap the AI call in an inner `try/finally`.

---

### BUG-12: Dashboard::generateAiSummary() — fragile AI usage log capture via `latest()->first()`

- **Severity:** MEDIUM (CVSS 5.5)
- **Impact:** 2 (wrong cost displayed to user) | **Exploitability:** 2 (requires concurrent AI calls) | **Scope:** 1.5
- **Location:** `app/Livewire/Dashboard.php:214-217`
- **Detail:** Uses `AiUsageLog::query()->where('user_id', Auth::id())->latest()->first()` to capture AI usage. This is the exact fragile pattern that was fixed in BUG-5 for TrafficSources. Under concurrent AI calls for the same user, this may return another component's usage log. Other components (`ShortsExplorer`, `ContentCalendarGenerator`) correctly use the `$beforeMaxId = AiUsageLog::max('id') ?? 0` pattern.
- **Fix:** Apply the `$beforeMaxId` pattern: capture `AiUsageLog::max('id')` before the AI call, then query `->where('id', '>', $beforeMaxId)->first()` after.

---

### BUG-13: SyncChannelData job lacks `ShouldBeUnique` — concurrent duplicate syncs possible

- **Severity:** MEDIUM (CVSS 5.0)
- **Impact:** 3 (duplicate API calls, quota waste, data races during purge+resync) | **Exploitability:** 2 (user clicks "Sync" twice, or scheduled + manual overlap) | **Scope:** 0
- **Location:** `app/Jobs/SyncChannelData.php`
- **Detail:** None of the 9 jobs implement `ShouldBeUnique`. For `SyncChannelData` specifically, this is risky because: (1) A user can trigger manual sync from Settings while a scheduled sync is already running. (2) With `forceResync: true`, two concurrent jobs would both call `purgeChannelData()` then `sync()`, causing data races. (3) YouTube API quota is consumed twice unnecessarily. The `$tries = 3` with `$backoff = 60` makes overlapping retries more likely.
- **Fix:** Implement `ShouldBeUnique` with `uniqueId()` returning `$this->channel->id` and a reasonable `$uniqueFor` timeout (e.g., 600 seconds).

---

### BUG-14: Settings::deleteAccount() — no transaction wrapping channel + user deletion

- **Severity:** MEDIUM (CVSS 4.5)
- **Impact:** 3 (orphaned data if partial failure) | **Exploitability:** 1 (requires crash during deletion) | **Scope:** 0.5
- **Location:** `app/Livewire/Settings.php:307-322`
- **Detail:** `deleteAccount()` performs: (1) `$user->channel->forceDelete()`, (2) `Auth::logout()`, (3) `$user->delete()`, (4) session invalidation — all without a transaction. If the process crashes after channel deletion but before user deletion, the user record becomes orphaned with no channel. Similarly, `disconnectChannel()` at line 263-268 soft-deletes the channel then nullifies OAuth tokens on the user in separate operations without a transaction.
- **Fix:** Wrap channel deletion + user deletion in `DB::transaction()`.

---

### BUG-15: Dashboard::getTrendData() — redundant query for shorts video IDs

- **Severity:** LOW (CVSS 2.5)
- **Impact:** 1 (unnecessary DB query per render) | **Exploitability:** 3 (every dashboard page load) | **Scope:** 0
- **Location:** `app/Livewire/Dashboard.php:150`
- **Detail:** `getTrendData()` calls `$channel->videos()->where('type', VideoType::Short)->pluck('id')` at line 150 to get shorts video IDs, even though `getFilteredVideoIds()` was already called at line 132. When `contentFilter` is `'all'`, the filtered IDs already include shorts. When `contentFilter` is `'shorts'`, the filtered IDs ARE the shorts IDs. This is a redundant query in 2 of 3 filter modes.
- **Fix:** Reuse `$filteredVideoIds` or compute shorts IDs from the already-fetched set.

---

### BUG-16: GoogleAuthController::callback() — user + channel creation without transaction

- **Severity:** LOW (CVSS 2.0)
- **Impact:** 2 (orphaned user without channel on partial failure) | **Exploitability:** 1 (requires crash during OAuth callback) | **Scope:** 0
- **Location:** `app/Http/Controllers/GoogleAuthController.php:63-106`
- **Detail:** The callback creates/updates a user (line 64-80), marks email as verified (line 83-85), creates a channel (line 92-97), and dispatches a sync job (line 99) — all as separate operations without a transaction. If the YouTube API call at line 90 fails (which IS caught), the user is created but has no channel. While this is partially handled by the try-catch, the user creation + email verification themselves are not atomic.
- **Fix:** Wrap user creation + email verification in `DB::transaction()`. The channel creation try-catch is acceptable since it's a separate concern.

---

## Code Smells (Open)

| # | Type | Location | Description | Status |
|---|---|---|---|---|
| CS-2 | **God Class** | `ContentPlanner.php` (501 lines) | Themes, ideas, calendar, scheduling, tag management | Open |
| CS-3 | **God Class** | `ShortsExplorer.php` (538 lines) | Video listing + detail + hook analysis + hook ideas | Open |
| CS-4 | **God Component** | `Settings.php` (349 lines) | Profile, timezone, digest, sync, resync, disconnect, deletion | Open |
| CS-5 | **God Component** | `Dashboard.php` (290 lines) | Metric aggregation mixed with view logic | Open |
| CS-7 | **Feature Envy** | `TrafficSources.php` | 80+ lines of raw SQL aggregation in a component | Open |
| CS-8 | **Magic Numbers** | `HealthScoreService`, `PostingTimeService`, `QuotaTracker` | Hardcoded thresholds | Open |
| CS-9 | **Global Mutable State** | `AiContext.php` | `app()->instance()` not request-scoped | Open |
| CS-11 | **Long Method** | `PostingTimeService` (543 lines) | Too many concerns in one class | Open |
| CS-13 | **Inconsistent AiContext pattern** | `Dashboard.php`, `ContentPlanner.php` | Some components use inner try/finally, some don't | New |
| CS-14 | **Inconsistent AI usage capture** | `Dashboard.php` | Uses `latest()->first()` while siblings use `$beforeMaxId` | New |

---

## Code Health

### Score Breakdown

| Category | Score | Max | Notes |
|---|---|---|---|
| **Readability** | 16 | 20 | Clean code, good naming, proper PHPDoc. Deductions for God classes and magic numbers. |
| **Maintainability** | 14 | 20 | Previous duplication fixes helped (+1). Still has God components and inconsistent patterns across components. |
| **Test Coverage** | 18 | 20 | Excellent: 848 tests, 2081 assertions, all passing. +1 from previous (35 new tests). SQLite-only testing still a gap. |
| **Modularity** | 15 | 20 | Good service layer. Deductions for God components and flat directory structure. |
| **Dependency Health** | 15 | 20 | Clean dependency management. AiContext global state remains. |
| **Total** | **78** | **100** | **Rating: Moderate** |

---

## Project Structure

### Issues (unchanged from previous report)
1. **Livewire directory is flat** — 38+ components with no subdirectory grouping
2. **Services directory is flat** — 20 services with no logical grouping
3. **No DTOs/Value Objects** — Complex analytics data passed as raw arrays
4. **No custom exception classes** — Domain errors not distinguished from system errors

### Suggestions (unchanged)
1. Group Livewire: `Analytics/`, `Content/`, `Settings/`, `AI/`, `Competitors/`
2. Group services: `YouTube/`, `Analytics/`, `AI/`, `Growth/`
3. Add `app/DataTransferObjects/` for structured data
4. Add custom exceptions: `QuotaExceededException`, `SyncFailedException`, `OAuthFailedException`

---

## Architecture

### Detected Pattern
**MVC + Service Layer + Agent/Tool Pattern** — unchanged from previous report.

### New Observations
- **Inconsistent defensive patterns**: The codebase has good patterns (`$beforeMaxId`, `try/finally` for AiContext) but they're not applied uniformly. Dashboard.php missed both fixes that were applied to sibling components.
- **No job uniqueness**: 9 queued jobs, none implement `ShouldBeUnique`. For data-mutating jobs like `SyncChannelData`, this creates race condition risk.
- **Account deletion atomicity**: Critical destructive operations (channel purge, account deletion) lack transaction wrapping.

---

## Refactor Plan

### Priority 1 — Fix Active Bugs (1 day)
1. **BUG-11**: Move `AiContext::clear()` to `finally` block in `Dashboard::generateAiSummary()`
2. **BUG-12**: Apply `$beforeMaxId` pattern to `Dashboard::generateAiSummary()` AI usage capture
3. **BUG-13**: Add `ShouldBeUnique` to `SyncChannelData` job
4. **BUG-14**: Wrap `Settings::deleteAccount()` in `DB::transaction()`

### Priority 2 — Consistency Pass (1 day)
5. Audit ALL 20 `AiContext::bind()` call sites — ensure every one has a matching `clear()` in a `finally` block
6. Audit ALL AI usage log captures — ensure all use `$beforeMaxId` pattern, not `latest()->first()`
7. Consider adding `ShouldBeUnique` to other data-mutating jobs (`TagVideos`, `ComputeChannelHealthScore`)

### Priority 3 — Structural (1 week, unchanged)
8. Split God components (ContentPlanner, ShortsExplorer, Settings)
9. Organize Livewire/Services into subdirectories
10. Add custom exception classes
11. Add MySQL integration tests

---

## Test Results

| Metric | Value |
|---|---|
| **Total Tests** | 848 |
| **Passed** | 848 |
| **Failed** | 0 |
| **Assertions** | 2081 |
| **Duration** | 55.32s |

---

## CI/CD Quality Gate

| Gate | Threshold | Actual | Status |
|---|---|---|---|
| Health score >= 70 | 70 | 78 | **PASS** |
| Health drop <= 10 | <= 10 | +2 (improved) | **PASS** |
| No critical bugs | 0 | 0 | **PASS** |
| All tests pass | 100% | 100% | **PASS** |

### **CI Status: PASS**

> 6 new bugs found (1 HIGH, 3 MEDIUM, 2 LOW). The HIGH bug (BUG-11) is the same AiContext leak pattern previously fixed in TrafficSources — Dashboard.php was missed. BUG-12 is the same fragile AI usage capture pattern. Both are quick fixes. BUG-13 (missing ShouldBeUnique) is the most architecturally significant new finding. All 10 previous bugs remain fixed.

---

*Report generated on 2026-04-23*
