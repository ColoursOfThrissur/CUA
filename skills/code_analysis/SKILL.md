# code_analysis skill

Routes code quality queries to `CodeAnalysisTool`.

## Operations

| Operation | What it does |
|---|---|
| `get_file_metrics` | Complexity, maintainability index (0-100), lines, comment ratio |
| `detect_issues` | Dead code, long functions, bare excepts, too many params |
| `get_dependencies` | Import graph, unused imports, circular deps, external ratio |
| `get_change_impact` | What imports this file, test coverage, registry entry |
| `get_code_review` | All layers + LLM advisor: refactor candidates, quick wins, risks |

## Evolution pipeline integration

`get_code_review` output feeds directly into the evolution proposal generator —
`evolution_priority` maps to EVOLVE_URGENT / EVOLVE_RECOMMENDED / MONITOR / HEALTHY.
