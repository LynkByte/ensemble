# Example Scenario: Building a Laravel Smart Todo App

> A realistic walkthrough showing how `ensemble-mcp` enhances an AI coding agent (OpenCode) while a developer builds a Laravel application from scratch.

**Goal:** Demonstrate the invisible value of ensemble-mcp tools during a real development workflow. The developer never interacts with ensemble-mcp directly — it runs behind the scenes, making the agent smarter, cheaper, and more reliable.

---

## Prerequisites

- OpenCode installed and configured with an LLM provider
- `ensemble-mcp` installed and registered:

```bash
pip install ensemble-mcp
ensemble-mcp install --tools opencode
```

This adds the MCP server entry to OpenCode's config:

```json
// config.json or ~/.config/opencode/config.json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "ensemble": {
      "type": "local",
      "command": ["uvx", "ensemble-mcp"]
    }
  }
}
```

**Important:** The installer also copies agent files into tool-specific directories (e.g. `.opencode/agents/` for OpenCode) and a workflow skill file (e.g. `.opencode/skills/ensemble-mcp-workflow/SKILL.md` for OpenCode). This skill file is what tells the AI agent **when and how** to call ensemble-mcp tools. Without it, the tools are available but the agent won't know to use them. See the [Uninstall Guide](UNINSTALL.md) to reverse this setup.

---

## The Project

**SmartTodo** — a Laravel todo application with "smart" features:

- User authentication (Laravel Breeze)
- Full CRUD for todos
- Auto-categorization based on title keywords
- Auto-priority based on urgency keywords and due dates
- Duplicate detection using string similarity
- Dashboard with stats
- REST API with tests

---

## Session 1: Project Scaffolding

The developer opens a terminal and starts a new project:

```bash
mkdir smart-todo && cd smart-todo
laravel new . --no-interaction
opencode
```

Then types:

```
Set up a smart todo application with Laravel. I need:
- User auth (use Breeze)
- A "todos" table with: title, description, category, priority (1-5),
  is_completed, due_date, user_id
- A simple auto-categorizer that assigns category based on keywords
  in the title (e.g. "buy groceries" → "shopping", "fix bug" → "work")
- REST API + Blade views
Start with the migration, model, and auth scaffolding.
```

### What ensemble-mcp does (behind the scenes)

| Tool Called | Purpose |
|---|---|
| `metrics_start_session` | Starts tracking this session — `task: "Laravel smart todo setup"`, `classification: "standard"` |
| `model_recommend` | Agent asks which model to use — `agent: "scope"`, `task_classification: "standard"` → returns `tier: "mid"` (sonnet, not opus — saves cost) |
| `patterns_search` | Searches for past patterns matching `"laravel project setup auth migration"` — empty on first project |
| `project_index` | Indexes the fresh Laravel scaffold so the agent knows every file and class |

The agent then:

1. Runs `composer require laravel/breeze --dev` and `php artisan breeze:install blade`
2. Creates the migration:

```php
Schema::create('todos', function (Blueprint $table) {
    $table->id();
    $table->foreignId('user_id')->constrained()->cascadeOnDelete();
    $table->string('title');
    $table->text('description')->nullable();
    $table->string('category')->default('general');
    $table->unsignedTinyInteger('priority')->default(3);
    $table->boolean('is_completed')->default(false);
    $table->date('due_date')->nullable();
    $table->timestamps();
});
```

3. Creates the `Todo` model with fillable fields and relationships
4. Creates `app/Services/TodoCategorizer.php` with keyword-to-category mapping

### After completion

| Tool Called | Purpose |
|---|---|
| `drift_check` | Verifies changes match the task — `changed_files: ["migration", "Todo.php", "TodoCategorizer.php", ...]` → `verdict: "aligned"`, `score: 0.12` |
| `patterns_store` | Saves the approach: `name: "laravel todo crud setup"`, `approach: "Breeze for auth, service class for business logic"` |
| `metrics_record_step` | Records token usage: `agent: "craft"`, `input_tokens: 8200`, `output_tokens: 3400` |
| `metrics_end_session` | Closes session with `status: "completed"` |

---

## Session 2: Building the CRUD

Next day, the developer continues:

```
Build the full CRUD for todos:
- TodoController with index, create, store, show, edit, update, destroy
- Blade views using the Breeze layout
- Auto-categorize on store and update
- Only show the logged-in user's todos
- Validation: title required max:255, due_date must be future
```

### What ensemble-mcp does

| Tool Called | Purpose |
|---|---|
| `metrics_start_session` | New tracking session — `classification: "standard"` |
| `patterns_search` | Finds the pattern from Session 1 — agent learns the developer prefers service classes, so it injects `TodoCategorizer` into the controller via constructor injection |
| `project_query` | `query: "TodoCategorizer"`, `file_types: ["php"]` — locates the service class instantly |
| `project_dependencies` | `file_path: "app/Models/Todo.php"` — knows the model's relationships and casts |

The agent builds:

- `TodoController` with all 7 resource methods
- `StoreTodoRequest` and `UpdateTodoRequest` form requests
- Blade views: `index.blade.php`, `create.blade.php`, `edit.blade.php`, `show.blade.php`
- Routes in `web.php`

### Mid-session scope change

The developer adds a request:

```
Actually, also add soft deletes to todos and a "trash" view.
```

| Tool Called | Result |
|---|---|
| `drift_check` | `score: 0.25`, `verdict: "aligned"` — soft deletes are closely related to todo CRUD |
| `session_save` | Checkpoints progress in case of crash — `state: {step: "adding soft deletes", files_modified: [...]}` |

**Contrast — if the developer had asked** *"also add a blog system"*:

| Tool Called | Result |
|---|---|
| `drift_check` | `score: 0.72`, `verdict: "significant_drift"` |

The agent would respond:

> "Adding a blog system is outside the current task scope (todo CRUD). Want me to finish the todo CRUD first, then start a new session for the blog?"

This prevents scope creep and keeps each session focused.

---

## Session 3: Smart Features

```
Now make it smart:
1. Auto-priority: if title contains "urgent" or "asap", set priority to 5.
   If due_date is within 24 hours, bump priority by 2 (max 5).
2. Duplicate detection: before saving, check if the user has a todo with
   similar title (levenshtein distance < 5). Warn but still allow save.
3. Dashboard widget: overdue count, today's tasks, completion rate this week.
```

### What ensemble-mcp does

| Tool Called | Purpose |
|---|---|
| `model_recommend` | `agent: "craft"`, `task_classification: "standard"` → `tier: "mid"` |
| `patterns_search` | Queries `"duplicate detection levenshtein string similarity"` and `"laravel dashboard stats aggregation"` — checks for past solutions |
| `project_query` | Finds existing service classes to extend rather than creating new ones |

The agent builds:

```php
// app/Services/TodoSmartService.php

class TodoSmartService
{
    public function autoPriority(Todo $todo): int
    {
        $priority = $todo->priority;

        if (preg_match('/\b(urgent|asap|critical)\b/i', $todo->title)) {
            $priority = 5;
        }

        if ($todo->due_date && $todo->due_date->diffInHours(now()) <= 24) {
            $priority = min(5, $priority + 2);
        }

        return $priority;
    }

    public function findDuplicates(User $user, string $title): Collection
    {
        return $user->todos()
            ->where('is_completed', false)
            ->get()
            ->filter(fn (Todo $todo) => levenshtein(
                strtolower($todo->title),
                strtolower($title)
            ) < 5);
    }
}
```

### After completion

| Tool Called | What gets stored |
|---|---|
| `patterns_store` | `name: "fuzzy duplicate detection"`, `approach: "PHP levenshtein() with threshold, flash warning to user"`, `outcome: "Works well for short strings like todo titles"` |
| `patterns_store` | `name: "laravel dashboard aggregation"`, `approach: "Eloquent queries with whereDate and selectRaw for stats"`, `outcome: "Fast enough for single-user dashboards"` |

---

## Session 4: API and Tests

```
Add a REST API under /api/v1/todos with the same CRUD + smart features.
Use API resources. Write feature tests for everything.
```

### What ensemble-mcp does

| Tool Called | Purpose |
|---|---|
| `patterns_search` | Finds CRUD pattern — applies it to API context automatically |
| `project_query` | `query: "TodoController"` — finds the web controller to mirror logic |
| `project_dependencies` | Maps all service classes the API controller needs to inject |

The agent builds:

- `app/Http/Controllers/Api/V1/TodoController.php`
- `app/Http/Resources/TodoResource.php` and `TodoCollection.php`
- `routes/api.php` with versioned prefix
- `tests/Feature/Api/TodoApiTest.php` — ~15 test cases:

```php
public function test_store_auto_categorizes(): void
{
    $response = $this->actingAs($this->user)
        ->postJson('/api/v1/todos', [
            'title' => 'Buy groceries for dinner',
            'due_date' => now()->addDays(1)->toDateString(),
        ]);

    $response->assertStatus(201)
        ->assertJsonPath('data.category', 'shopping');
}

public function test_store_detects_duplicates(): void
{
    Todo::factory()->create([
        'user_id' => $this->user->id,
        'title' => 'Fix the login bug',
    ]);

    $response = $this->actingAs($this->user)
        ->postJson('/api/v1/todos', [
            'title' => 'Fix the login bugs',
        ]);

    $response->assertStatus(201)
        ->assertJsonPath('meta.duplicate_warning', true);
}
```

- `tests/Feature/TodoSmartServiceTest.php` — unit tests for categorizer, priority, dedup

---

## One Week Later: Cost Review

The developer asks:

```
How much have my AI sessions cost this week?
```

### What ensemble-mcp returns

| Tool Called | Output |
|---|---|
| `metrics_trend(days=7)` | Aggregated cost data |

```
Last 7 days
────────────────────────────────────────
Sessions:         6
Total input:      89,400 tokens
Total output:     24,100 tokens
Estimated cost:   $0.63
Avg per session:  $0.11

By agent:
  scope  (planner)   $0.14  (22%)
  craft  (coder)     $0.41  (65%)
  lens   (reviewer)  $0.08  (13%)

Top sessions by cost:
  1. "Build todo CRUD"        $0.18
  2. "Smart features"         $0.15
  3. "API and tests"          $0.14
  4. "Project scaffolding"    $0.09
```

The developer can also compare sessions:

```
Compare the CRUD session to the smart features session.
```

| Tool Called | Insight |
|---|---|
| `metrics_compare(session_id_a, session_id_b)` | Smart features used 40% more tokens but completed in fewer agent steps — pattern reuse from Session 1 reduced exploration time |

---

## One Month Later: Skills Emerge

After building multiple Laravel projects, the developer has accumulated 20+ stored patterns. ensemble-mcp detects clusters automatically.

| Tool Called | Result |
|---|---|
| `skills_suggest(project_path="...")` | Finds a cluster of 6 patterns around "Laravel service class architecture" |
| `skills_generate(suggestion_id=1, action="accept")` | Writes a skill file to `.ai/skills/` |

Generated file — `.ai/skills/laravel-service-pattern.md`:

```markdown
# Laravel Service Class Pattern

## When to apply
Any Laravel project where business logic is needed beyond simple CRUD.

## Approach
- Extract business logic into dedicated service classes under `app/Services/`
- Inject services into controllers via constructor injection
- Keep controllers thin — only HTTP concerns (validation, response formatting)
- Name services after their domain: `TodoCategorizer`, `TodoSmartService`
- One service per responsibility, not one mega-service per model

## Testing
- Unit test services directly (no HTTP layer)
- Feature test controllers for integration
- Use factories for test data

## Examples from past sessions
- TodoCategorizer: keyword-based auto-categorization
- TodoSmartService: priority calculation, duplicate detection
- DashboardService: aggregation queries for stats widgets
```

**From this point forward**, every new Laravel project the developer works on automatically loads this skill. The agent follows the developer's preferred architecture from the first prompt — no re-explaining needed.

---

## Summary: What the Developer Experiences vs. What Happens

### What the developer sees

A fast, accurate AI agent that:
- Remembers their architectural preferences across sessions
- Catches scope creep before it happens
- Gets smarter with each project
- Uses affordable models without sacrificing quality

### What ensemble-mcp provides

| Capability | Tool | Developer Benefit |
|---|---|---|
| Pattern memory | `patterns_search` / `patterns_store` | Agent reuses approaches that worked before |
| Cost optimization | `model_recommend` | Cheapest viable model per task — ~60% savings vs always using opus |
| Scope control | `drift_check` | Changes stay on-task, no silent scope creep |
| Cost visibility | `metrics_trend` / `metrics_session_report` | Full token/cost audit trail |
| Crash recovery | `session_save` / `session_load` | Resume mid-task after terminal close or crash |
| Codebase awareness | `project_index` / `project_query` / `project_dependencies` | Agent navigates the codebase without re-exploring from scratch |
| Learned skills | `skills_suggest` / `skills_generate` | Patterns crystallize into permanent project skills |

### Key point

The developer **never types an ensemble-mcp command**. They just talk to OpenCode naturally. ensemble-mcp runs as a background MCP server, and the AI agent calls its tools automatically at the right moments.

---

## Final Project Structure

```
smart-todo/
├── app/
│   ├── Http/
│   │   ├── Controllers/
│   │   │   ├── Api/V1/TodoController.php
│   │   │   ├── DashboardController.php
│   │   │   └── TodoController.php
│   │   ├── Requests/
│   │   │   ├── StoreTodoRequest.php
│   │   │   └── UpdateTodoRequest.php
│   │   └── Resources/
│   │       ├── TodoCollection.php
│   │       └── TodoResource.php
│   ├── Models/
│   │   ├── Todo.php
│   │   └── User.php
│   └── Services/
│       ├── TodoCategorizer.php
│       └── TodoSmartService.php
├── database/
│   ├── factories/
│   │   └── TodoFactory.php
│   └── migrations/
│       └── xxxx_xx_xx_create_todos_table.php
├── resources/views/
│   ├── dashboard.blade.php
│   └── todos/
│       ├── index.blade.php
│       ├── create.blade.php
│       ├── edit.blade.php
│       ├── show.blade.php
│       └── trash.blade.php
├── routes/
│   ├── api.php
│   └── web.php
├── tests/Feature/
│   ├── Api/TodoApiTest.php
│   ├── TodoCrudTest.php
│   └── TodoSmartServiceTest.php
└── .ai/skills/
    └── laravel-service-pattern.md    ← auto-generated by ensemble-mcp
```
