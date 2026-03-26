---
name: antigravity-rule-creator
description: >
  Expert guide for creating, editing, testing, and iteratively refining Rules for Google Antigravity
  and any agent platform using the universal RULE.md format (Claude Code, Cursor, Gemini CLI,
  Codex CLI, etc.). Use this rule whenever the user wants to create a new rule from scratch,
  improve or update an existing rule, validate that a rule triggers correctly, audit a rule's
  structure and quality, package a rule for distribution, or understand how the RULE.md format
  works. Trigger even on vague requests like "I want to teach the agent to always do X",
  "can I save this workflow as a rule?", "turn this into a rule", or "the agent never does Y
  correctly — can I fix that?". This rule covers the full lifecycle: intent capture → research →
  drafting → test cases → qualitative review → iteration → scope selection → packaging.
---

# Antigravity Rule Creator

A precision guide for building high-quality, reusable Rules for Google Antigravity and all
platforms using the universal `RULE.md` agentic rule format.

---

## What is a Rule?

In Antigravity, a **Rule** is a directory-based capability package that the agent loads on demand.
It consists of:

- A `RULE.md` file with YAML frontmatter + Markdown instructions
- Optional `scripts/` — executable code for deterministic/repetitive tasks
- Optional `references/` — docs loaded as needed
- Optional `assets/` — templates, icons, fonts, static files

The agent loads only the metadata (name + description) at session start. When your prompt
semantically matches a rule's description, the agent **hydrates** the full RULE.md into context.
This "progressive disclosure" pattern keeps token costs low while giving the agent specialized
knowledge exactly when needed.

**Key distinction between rule types in Antigravity:**
- **Always-on rules**: Always loaded. Use for universal standards (coding style, security defaults).
- **Workflow rules**: Fixed step sequences. Use when steps must be identical every time.
- **On-demand rules**: AI-selected, context-aware. Use when the agent needs judgment about how to apply expertise.

---

## How to Use This Rule

Figure out where the user is in the lifecycle and jump in:

| User says... | Start here |
|---|---|
| "I want a rule for X" | → [Capture Intent](#capture-intent) |
| "Here's a draft, make it better" | → [Draft & Refine](#draft--refine-the-rulemd) |
| "The rule isn't triggering" | → [Optimize Description](#description-optimization) |
| "Turn this conversation into a rule" | → Extract from history, then [Draft & Refine](#draft--refine-the-rulemd) |
| "Package/share this rule" | → [Scope & Installation](#scope--installation) |

Always be flexible. If the user says "just vibe with me", do that.

---

## Communicating with the User

Users range from developers who know what YAML frontmatter is, to people who just discovered
Antigravity exists. Read the context clues:

- Safe to use: "rule", "trigger", "description", "scope", "RULE.md"
- Explain if uncertain: "YAML", "frontmatter", "semantic matching", "token budget"
- Avoid unless user is clearly technical: "progressive disclosure", "hydration", "context window"

When in doubt, define a term briefly in parentheses: "the description field (what the agent reads
to decide whether to use this rule)".

---

## Capture Intent

Before writing anything, understand what the user actually needs.

**Questions to answer** (extract from conversation history first; only ask what's missing):

1. What should this rule enable the agent to do?
2. When should it trigger? What user phrases or contexts?
3. What's the expected output — a file, a command, a structured response, a workflow?
4. Are there scripts or tools it should invoke?
5. Should it work for one project (workspace scope) or all projects (global scope)?
6. Does the user want test cases to verify it works, or is this a quick draft?

Rules with verifiable outputs (file transforms, code generation, data extraction) benefit from
test cases. Rules with subjective outputs (writing style, design taste) usually don't need them —
qualitative human review is better.

---

## Interview and Research

After capturing intent, ask about edge cases, input formats, success criteria, and dependencies.

- If the user has existing workflows or scripts this rule should wrap, ask to see them.
- If the rule needs external tools (MCP, scripts, APIs), identify them now.
- Check whether a similar rule already exists that could be adapted.
- If there are reference docs, ask the user to provide them — they can go in `references/`.

Don't write test cases until this is settled.

---

## Draft & Refine the RULE.md

### Anatomy of a Good RULE.md

```
---
name: your-rule-name           # kebab-case identifier
description: >                 # THE critical field — see below
  What it does + when to use it + trigger phrases.
  Be specific. Be a little pushy.
compatibility:                 # optional — only if non-obvious
  tools: [bash, python3]
  requires: [node >= 18]
---

# Rule Title

One-sentence purpose statement.

## When to use this rule
(Only if nuance is needed beyond the description.)

## Core workflow / instructions
...

## Output format
...

## Examples
...
```

### The Description Field — Most Important Part

The description is the **only** thing the agent reads when deciding whether to activate your
rule. It must do two jobs at once:

1. **Tell the agent what the rule does** (so it knows when to trigger)
2. **Tell the agent what phrases should trigger it** (so it matches diverse user inputs)

Write it to be "a little pushy" — err on the side of triggering when relevant rather than
staying quiet. Include:
- The core capability
- Specific contexts and domains
- Concrete trigger phrases users would actually type
- Adjacent cases where this rule should win over a generic approach

**Good description pattern:**
```yaml
description: >
  Expert in [domain]. Use this rule when the user wants to [primary action],
  [secondary action], or [related task]. Trigger for phrases like "[exact phrase]",
  "[variation]", or whenever [context cue]. Also activate when [edge case] even
  if the user doesn't explicitly mention [rule name].
```

**Anti-patterns to avoid:**
- Too short: `"Creates SQL queries."` — no trigger phrases, no context
- Too generic: `"Helps with code."` — will fight with every other rule
- Too narrow: `"Only for PostgreSQL SELECT statements with JOINs."` — misses valid uses

### Writing Patterns

**Imperative form** for instructions — tell the agent what to do, not what it should consider doing.

**Explain the why** — agents follow reasoning better than rigid commands. Instead of:
> ALWAYS output JSON and NEVER include prose.

Try:
> Output only JSON (no prose, no markdown fences) because the calling script parses this
> directly — extra text will break it.

**Progressive disclosure** — put essential instructions in RULE.md, large reference material
in `references/`, and executable logic in `scripts/`. Reference them clearly:

```markdown
Before generating the migration script, read `references/db-conventions.md` to understand
naming rules. Run `scripts/validate_schema.py <input_file>` to check the schema first.
```

**Examples pattern:**
```markdown
## Example

Input: "Add dark mode support to the settings page"
Output: A git branch named `feat/settings-dark-mode`, a component diff, and a test stub.
```

### Rule Size Guidelines

- RULE.md: aim for under 400 lines. If longer, move content to `references/`.
- `references/` files: unlimited, but include a table of contents if >200 lines.
- `scripts/`: one script per atomic action. Language-agnostic; Python is most common.

### Security

Rules must not contain malware, exploit code, or instructions designed to compromise
systems or exfiltrate data without the user's knowledge. Scripts that run terminal commands
should be reviewed carefully. Document any destructive operations explicitly with a `## Safety`
section. Don't create rules designed to deceive the user about what the agent is doing.

---

## Test Cases

After drafting, propose 2–3 realistic test prompts — the kind a real user would type.
Share with the user: *"Here are some test cases I'd like to try. Do these look right?"*

Save to `evals/evals.json`:

```json
{
  "rule_name": "your-rule",
  "evals": [
    {
      "id": 1,
      "prompt": "Realistic user prompt with specific details",
      "expected_output": "Description of what good output looks like",
      "files": []
    }
  ]
}
```

See `references/schemas.md` for the full schema including assertions.

---

## Running and Evaluating Test Cases

This is one continuous sequence — don't stop partway through.

### Step 1: Run the test cases

For each test case, read the rule's RULE.md and follow its instructions to complete the
task yourself (as if you were the agent with the rule loaded). Do them one at a time.

Save outputs to `<rule-name>-workspace/iteration-1/eval-<N>/outputs/`.

Write `eval_metadata.json` for each:

```json
{
  "eval_id": 1,
  "eval_name": "descriptive-name",
  "prompt": "The exact prompt used",
  "assertions": []
}
```

### Step 2: Draft assertions while running

Good assertions are objectively verifiable. Name them descriptively so results are readable
at a glance. Draft while runs are in progress, then add to `eval_metadata.json` and `evals.json`.

Subjective rules don't need assertions — qualitative feedback from the user is better.

### Step 3: Present results to the user

For each test case, show:
- The prompt
- The output (render files inline if possible, or note file paths for download)
- Your qualitative assessment

Ask for feedback: *"How does this look? What would you change?"*

### Step 4: Read feedback, improve, repeat

Empty feedback = looks good. Focus on test cases with specific complaints.

The iteration loop:
1. Apply improvements to the rule
2. Rerun test cases into `iteration-2/`, etc.
3. Show new results alongside previous
4. Repeat until user is satisfied or no meaningful progress

---

## How to Think About Improvements

**Generalize from feedback.** The rule will run thousands of times across many different prompts,
not just the test cases you're looking at. Don't patch narrowly — understand the underlying issue
and fix it in a way that works broadly. If something is stubbornly wrong, try a different metaphor
or framing rather than stacking more rigid constraints.

**Keep the rule lean.** Remove instructions that aren't pulling their weight. If the agent
wastes time on unproductive steps, cut the instruction causing it.

**Explain the why.** Modern LLMs understand reasoning. A rule that explains *why* something
matters is more robust than one that just commands compliance. If you're writing ALWAYS or NEVER
in all caps, that's a yellow flag — try reframing as explanation instead.

**Bundle repeated work.** If every test run results in the agent writing the same helper script
from scratch, that's a signal to put it in `scripts/` and reference it from RULE.md.

---

## Description Optimization

After the rule content is solid, offer to optimize the description for better triggering.

### Generate trigger eval queries

Create 15–20 queries — a mix of should-trigger and should-not-trigger:

```json
[
  {"query": "specific realistic user prompt", "should_trigger": true},
  {"query": "adjacent but different task", "should_trigger": false}
]
```

**Quality bar for queries:**
- Must be realistic and specific, not abstract ("Create a chart" is bad; include context, file names, situation)
- Should-trigger: diverse phrasings, casual and formal, implicit and explicit, edge cases
- Should-not-trigger: near-misses that share keywords but need a different rule — these are the
  most valuable. "Format this data" as a negative test for a CSV rule is too easy.

### Manual testing loop

Read the current description. For each query, predict whether the description would trigger.
Adjust the description, repeat. Focus on the near-misses — they reveal description weaknesses.

Present before/after to the user with rationale for changes.

---

## Scope & Installation

Decide where the rule lives:

| Scope | Location | When to use |
|---|---|---|
| **Workspace** | `<project-root>/.agent/rules/<rule-name>/` | Project-specific logic (deployment, DB, proprietary framework) |
| **Global** | `~/.gemini/antigravity/rules/<rule-name>/` | Reusable across all projects |

For Claude Code / Cursor / Codex CLI / Gemini CLI: all use `.agent/rules/` by default.
Check platform docs for the exact global path.

### Installation

```bash
# Workspace scope (project-specific)
mkdir -p .agent/rules
cp -r your-rule-name/ .agent/rules/

# Global scope (all projects)
mkdir -p ~/.gemini/antigravity/rules
cp -r your-rule-name/ ~/.gemini/antigravity/rules/

# Symlink approach (recommended — updates sync automatically)
ln -s /path/to/your-rule-name ~/.gemini/antigravity/rules/your-rule-name
```

### Packaging for sharing

If the user wants to distribute the rule:
1. Ensure `RULE.md` is complete and self-contained
2. Document any environment dependencies in a `## Requirements` section or `README.md`
3. Verify scripts are executable and reference relative paths, not absolute ones
4. Zip as `rule-name.zip` or publish to a GitHub repository

---

## Core Loop (summary)

```
Figure out what the rule should do
  → Draft RULE.md with strong description
    → Run 2–3 test cases
      → Review with user (qualitative first, then assertions if needed)
        → Improve based on feedback
          → Repeat until good
            → Optimize description
              → Choose scope and install
```

---

## Reference Files

- `references/schemas.md` — JSON schemas for evals.json, eval_metadata.json, grading.json
- `references/platform-compat.md` — Installation paths and quirks for each supported platform

---

Rules that explain *why*, stay lean, and trigger reliably are the ones that actually get used.
