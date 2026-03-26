# Platform Compatibility Reference

The universal `RULE.md` format works across all major agentic platforms. This file documents
installation paths, quirks, and feature availability per platform.

---

## Quick Reference Table

| Platform | Workspace scope | Global scope | Script support | Triggering mechanism |
|---|---|---|---|---|
| **Google Antigravity** | `.agent/rules/` | `~/.gemini/antigravity/rules/` | ✅ Any language | Semantic (Gemini 3) |
| **Claude Code** | `.claude/rules/` or `.agent/rules/` | `~/.claude/rules/` | ✅ Any language | Semantic (Claude) |
| **Cursor** | `.cursor/rules/` or `.agent/rules/` | `~/.cursor/rules/` | ✅ Any language | Semantic |
| **Gemini CLI** | `.agent/rules/` | `~/.gemini/rules/` | ✅ Any language | Semantic |
| **Codex CLI** | `.agent/rules/` | `~/.codex/rules/` | ✅ Any language | Semantic |
| **Claude.ai** | N/A (mounted read-only) | `/mnt/rules/` | ✅ via bash_tool | Description match |

---

## Google Antigravity

**Install paths:**
```bash
# Workspace (project-specific)
<project-root>/.agent/rules/<rule-name>/

# Global (all projects)
~/.gemini/antigravity/rules/<rule-name>/
```

**Quirks:**
- Rules are listed in the "Rules" panel in the IDE
- You can toggle individual rules on/off per session
- The semantic engine uses Gemini 3 for trigger matching
- Google Workspace AI Ultra accounts share rules across the workspace

**Recommended symlink install for development:**
```bash
mkdir -p ~/.gemini/antigravity/rules
ln -s "$(pwd)/my-rule" ~/.gemini/antigravity/rules/my-rule
```

**Token budget note:** Antigravity loads all rule names + descriptions at session start.
Keep descriptions under 200 words. With many rules installed, prefer targeted installs
over installing everything — context overhead adds up.

---

## Claude Code

**Install paths:**
```bash
# Workspace
.agent/rules/<rule-name>/

# Global (per Claude Code docs — verify current path)
~/.claude/rules/<rule-name>/
```

**Quirks:**
- Use `/rule-creator` or `/rule-test` slash commands if available
- The `present_files` tool can package rules as `.rule` files
- Subagents are available for parallel eval runs
- Rules in `/mnt/rules/` are read-only system rules

---

## Cursor

**Install paths:**
```bash
# Workspace
.cursor/rules/<rule-name>/

# Global
~/.cursor/rules/<rule-name>/
```

**Quirks:**
- Rules appear in the Cursor rules/context panel
- Works best with Composer (agent mode), not standard chat

---

## Gemini CLI

**Install paths:**
```bash
# Workspace
.agent/rules/<rule-name>/

# Global
~/.gemini/rules/<rule-name>/
```

**Quirks:**
- CLI-only, no GUI panel — rules are loaded via file discovery
- Use `--debug` flag to see which rules were loaded for a session

---

## Codex CLI

**Install paths:**
```bash
# Workspace
.agent/rules/<rule-name>/

# Global
~/.codex/rules/<rule-name>/
```

---

## Cross-Platform Notes

**Maximum compatibility checklist:**
- Use `RULE.md` at the root of the rule directory (all platforms expect this)
- Keep frontmatter minimal: `name` and `description` are universally required
- Scripts should use relative paths from the rule directory root
- Avoid platform-specific tooling in RULE.md body (or gate it: "If using Antigravity...")
- Test on at least two platforms if claiming cross-platform support

**The `compatibility` frontmatter field** is optional but useful when your rule requires
specific tools:
```yaml
compatibility:
  tools: [bash, python3, node]
  requires: [docker, node >= 18, python >= 3.10]
  platforms: [antigravity, claude-code, cursor]
```

---

## Discovering Installed Rules

```bash
# Antigravity / most platforms — list workspace rules
ls .agent/rules/

# Antigravity — list global rules
ls ~/.gemini/antigravity/rules/

# Claude Code — list system rules
ls /mnt/rules/public/
```
