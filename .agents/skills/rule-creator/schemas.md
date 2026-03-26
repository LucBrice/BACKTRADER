# Schemas Reference

JSON structures used by the antigravity-skill-creator eval and grading system.

## Table of Contents

1. [evals.json](#evalsjson)
2. [eval_metadata.json](#eval_metadatajson)
3. [grading.json](#gradingjson)
4. [benchmark.json](#benchmarkjson)

---

## evals.json

Master eval set for a skill. Saved in `evals/evals.json`.

```json
{
  "rule_name": "my-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "Realistic user prompt with context and specifics",
      "expected_output": "Description of what good output looks like",
      "files": ["path/to/input/file.csv"],
      "assertions": [
        {
          "name": "output-file-exists",
          "description": "The output file was created at the expected path",
          "type": "file_exists",
          "value": "outputs/result.csv"
        },
        {
          "name": "contains-header-row",
          "description": "Output CSV has the expected header row",
          "type": "file_contains",
          "value": "id,name,value"
        },
        {
          "name": "row-count-correct",
          "description": "Output has exactly 100 data rows",
          "type": "script",
          "script": "scripts/check_row_count.py",
          "args": ["outputs/result.csv", "100"]
        }
      ]
    }
  ]
}
```

### Assertion types

| type | description |
|------|-------------|
| `file_exists` | Check that a file exists at the given path |
| `file_contains` | Check that a file contains a specific string |
| `file_not_empty` | Check that a file is non-empty |
| `script` | Run a script and check exit code is 0 |
| `llm_judge` | Use an LLM to assess the output (for subjective criteria) |

For `llm_judge`, add a `rubric` field:
```json
{
  "name": "response-is-helpful",
  "type": "llm_judge",
  "rubric": "Is the output actionable and specific? Does it avoid vague generalities?"
}
```

---

## eval_metadata.json

Per-run metadata. Saved in `<workspace>/iteration-N/eval-<ID>/eval_metadata.json`.

```json
{
  "eval_id": 1,
  "eval_name": "csv-transform-with-header",
  "prompt": "The exact prompt used for this run",
  "skill_path": ".agent/skills/my-skill",
  "assertions": [
    {
      "name": "output-file-exists",
      "description": "The output file was created at the expected path"
    }
  ]
}
```

---

## grading.json

Assertion results. Saved in `<workspace>/iteration-N/eval-<ID>/with_skill/grading.json`.

```json
{
  "eval_id": 1,
  "eval_name": "csv-transform-with-header",
  "expectations": [
    {
      "text": "output-file-exists: The output file was created at the expected path",
      "passed": true,
      "evidence": "Found file at outputs/result.csv (2.4 KB)"
    },
    {
      "text": "contains-header-row: Output CSV has the expected header row",
      "passed": false,
      "evidence": "File exists but first line is 'data,data,data', not 'id,name,value'"
    }
  ],
  "pass_rate": 0.5,
  "total": 2,
  "passed": 1,
  "failed": 1
}
```

**Field names must be exactly**: `text`, `passed`, `evidence` — not `name`/`met`/`details`.

---

## benchmark.json

Aggregated results across all runs in an iteration.

```json
{
  "rule_name": "my-skill",
  "iteration": 1,
  "configurations": [
    {
      "name": "with_skill",
      "evals": [
        {
          "eval_id": 1,
          "eval_name": "csv-transform-with-header",
          "pass_rate": 1.0,
          "passed": 2,
          "total": 2
        }
      ],
      "summary": {
        "mean_pass_rate": 0.85,
        "stddev": 0.1,
        "total_evals": 3
      }
    },
    {
      "name": "without_skill",
      "evals": [...],
      "summary": {
        "mean_pass_rate": 0.45,
        "stddev": 0.2,
        "total_evals": 3
      }
    }
  ],
  "delta": {
    "mean_pass_rate": 0.40
  }
}
```
