"""Evaluation and benchmark harness for all 16 ensemble-mcp MCP tools.

Run all benchmarks:
    python evals/runner.py

Individual benchmarks via pytest:
    python -m pytest evals/ -v

Ad-hoc tool evaluation via CLI:
    python evals/cli.py list
    python evals/cli.py run <tool_name> [--key value ...]

Benchmark modules:
    bench_compress      — context_compress tool
    bench_patterns      — patterns_search, patterns_store, patterns_prune
    bench_drift         — drift_check tool
    bench_routing       — model_recommend tool
    bench_session       — session_save, session_load
    bench_indexer       — project_index, project_query, project_dependencies
    bench_skills        — skills_discover, skills_suggest, skills_generate
    bench_health_reset  — health, reset utility tools
"""
