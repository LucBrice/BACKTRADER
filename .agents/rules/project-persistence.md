---
trigger: model_decision
description: Project Persistence & Progress Tracking
---

# Project Persistence Rule

This rule ensures that all assistant agents preserve and recover the project context across different sessions, accounts, and conversations within the `BACKTRADER` workspace.

## 0. Scope (CRITICAL)
- **ONLY QUANT FACTS**: Record only information related to the **Quant R&D Blueprint (Sections 1-10)**.
- **EXCLUDE**: Metadata about the assistant, configuration prompts, administrative requests, or UI adjustments not related to trading research.
- **GOAL**: Maintain a technical "source of truth" for the trading strategy and its validation.

## 1. Mandatory Context Recovery (Start of Session)
- **ACTION (CRITICAL)**: Locate and read `PROJECT_STATE.md` at the very beginning of the session.
- **REASONING**: Any deviation from the recorded state leads to context fragmentation.
- **ALIGNMENT**: Use the "Roadmap" section to populate your `task.md`. If the roadmap is empty, your first task is to define it.

## 2. Mandatory State Synchronization (End of Every Turn)
- **UPDATE FREQUENCY**: You MUST evaluate the need for an update to `PROJECT_STATE.md` at the end of every task or major block of code changes.
- **TRIGGER (SYSTEMATIC)**:
    - **FEATURE**: Any new file creation or significant modification to `pipeline/` or `strategies/`.
    - **ARCHITECTURE**: Any change in directory structure or data flow MUST be reflected in the Mermaid diagram.
    - **DELETION**: Any file removal or decommissioning of a logic block.
    - **RESULTS**: Any new backtest GO/NO GO decision in Section 4.
- **TRACKING DELETIONS**: When code is removed, record WHAT was removed and WHY.

## 3. Standardized Structure
Maintain the following markdown structure to ensure consistent parsing by future agents:

```markdown
# Project State
## Status: [GO | NO GO | IN PROGRESS]
## Current Phase: [Blueprint Section]

## Research Context (80/20)
- **Assets Pool / Timeframes / Active Focus**

## Blueprint Compliance (Quant R&D Pipeline)
- [Checklist of 10 sections]

## Project Architecture & Communication Flow
```mermaid
graph TD
    [Mermaid Diagram]
```
- [Layer Descriptions]

## Active Features: [List of current tools/components]
## Accomplishments (Current Phase): [Bullet points]
## Archive (Previous Phases): [Historical summary]
## Roadmap: [Checklist of next steps]
```

## 4. Rule Quality & Self-Verification
- **SPECIFICITY**: Be explicit about file versions and specific bugs fixed.
- **SYSTEMATIC CHECK**: Before ending a turn, ask yourself: "Does `PROJECT_STATE.md` accurately reflect the new state of the workspace?"
- **ACTIONABILITY**: The "Roadmap" must contain clear items that a new agent can pick up immediately.

> [!IMPORTANT]
> This rule is **NON-NEGOTIABLE**. Failure to maintain the project state is considered a violation of the Quant Team Laws for project integrity.
