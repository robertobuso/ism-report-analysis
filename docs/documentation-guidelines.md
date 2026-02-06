# Documentation Guidelines — Envoy Financial Intelligence Suite

**Last Updated**: 2026-02-06

---

## 1. Core Principle: Single Source of Truth

Every domain in the suite has **ONE canonical status document** that is always current. This is the only place where the current state of that domain is described.

| Domain | Canonical Status Document |
|--------|--------------------------|
| Suite Integration | `docs/suite/status/current-implementation-status.md` |
| ISM Report Analysis | `docs/ism/status/current-implementation-status.md` |
| Financial News Analysis | `docs/news/status/current-implementation-status.md` |
| Portfolio Intelligence | `docs/portfolio-intelligence/status/current-implementation-status.md` |

**Rule**: If you need to know the current state of any domain, read its canonical status document. If information conflicts with another document, the status document wins.

---

## 2. When Completing a Feature

Every time a feature is completed, follow these steps **in order**:

### Step 1: Update the Status Document
Update the domain's canonical status document (`docs/<domain>/status/current-implementation-status.md`) to reflect what was built. This is **mandatory**.

### Step 2: Create an Implementation Document (if significant)
For non-trivial features, create an implementation document in `docs/<domain>/implementations/`. This captures architectural decisions, technical details, and lessons learned.

**Naming**: `YYYY-MM-DD-feature-name.md` (e.g., `2026-02-06-portfolio-crud-api.md`)

### Step 3: Archive Planning Documents
If the feature had planning documents (design docs, spike docs, etc.), archive them:
1. Add `**[ARCHIVED]**` header to the top of the document
2. Move the file to `docs/<domain>/archive/`
3. Update the archive README (`docs/<domain>/archive/README.md`)

### Step 4: Update the Domain README
If the feature changes the domain's capabilities or architecture, update `docs/<domain>/README.md`.

---

## 3. Archive Folder Discipline

### When to Archive
- Planning documents for completed features
- Superseded design documents
- Spike/investigation documents after conclusions are captured
- Status snapshots that have been replaced

### How to Archive

1. **Add the ARCHIVED header** at the very top of the file:
   ```markdown
   > **[ARCHIVED]** — This document is archived and may not reflect current implementation.
   > Superseded by: [Current Status](../status/current-implementation-status.md)
   > Archived on: 2026-02-06
   ```

2. **Move to archive folder**: `docs/<domain>/archive/`

3. **Update the archive README** (`docs/<domain>/archive/README.md`):
   ```markdown
   | Document | Archived Date | Superseded By |
   |----------|--------------|---------------|
   | portfolio-crud-api-design.md | 2026-02-06 | [Implementation](../implementations/2026-02-06-portfolio-crud-api.md) |
   ```

### What NOT to Archive
- The canonical status document (it gets updated in place, never archived)
- The domain README (it gets updated in place)
- Active planning documents for in-progress features

---

## 4. Red Flags for Stale Docs

Watch for these signs that documentation is going stale:

🚩 **Multiple documents claiming to be "current status"** — There should only be ONE per domain.

🚩 **Status document hasn't been updated in 2+ weeks during active development** — If code is changing, the status doc should be too.

🚩 **Planning document describes something that's already built** — It should be archived, with the status doc reflecting reality.

🚩 **Implementation details in the status doc contradict the codebase** — The status doc must match what's actually deployed.

🚩 **"TODO" or "Coming Soon" for features that already exist** — Update the doc immediately.

---

## 5. Preventing Search Confusion

When someone searches the codebase (or when Claude Code searches), archived documents can create confusion. Prevent this with:

### Archive READMEs
Every `archive/` folder must have a `README.md` that:
- Lists all archived documents with dates
- Explains WHY each was archived
- Links to the current replacement document

### ARCHIVED Headers
The `> **[ARCHIVED]**` header at the top of every archived file ensures that anyone (human or AI) who opens the file immediately knows it's not current.

### File Naming
- Status docs: `current-implementation-status.md` (always this exact name)
- Implementation docs: `YYYY-MM-DD-feature-name.md`
- Planning docs: Descriptive names (e.g., `analytics-engine-design.md`)
- Archived docs: Keep original name (the archive folder provides context)

---

## 6. Status Document Template

```markdown
# [Domain Name] — Current Implementation Status

**Last Updated**: YYYY-MM-DD
**Status**: 🟢 Production / 🟡 In Development / 🔴 Not Started

---

## Overview
Brief description of what this domain does and its current state.

## What's Working (Production)
- Feature A — brief description
- Feature B — brief description

## What's In Progress
- Feature C — current state, blockers, ETA
- Feature D — current state, blockers, ETA

## What's Not Started
- Feature E — brief description of planned work
- Feature F — brief description of planned work

## Architecture
Key technical decisions, stack, data flow.

## Known Issues
- Issue 1 — severity, workaround if any
- Issue 2 — severity, workaround if any

## Recent Changes
| Date | Change | Details |
|------|--------|---------|
| YYYY-MM-DD | Description | Link to implementation doc if applicable |
```

---

## 7. Implementation Document Template

```markdown
# [Feature Name] — Implementation

**Date**: YYYY-MM-DD
**Domain**: suite / ism / news / portfolio-intelligence
**Status Document Updated**: Yes / No (must be Yes before merging)

---

## Summary
What was built and why.

## Technical Decisions
Key architectural choices and their rationale.

## What Changed
- Files added/modified
- Database changes
- API changes
- UI changes

## Testing
How to verify this works.

## Follow-Up
Any remaining work, tech debt, or future improvements.
```

**Examples of good implementation doc names**:
- `2026-02-06-portfolio-crud-api.md`
- `2026-02-10-analytics-engine.md`
- `2026-02-15-tradestation-oauth.md`
- `2026-02-20-news-citation-fix.md`

---

## 8. Documentation Audit Checklist

Run this periodically (at least monthly during active development):

### Per Domain
- [ ] `docs/<domain>/status/current-implementation-status.md` exists and is current
- [ ] `docs/<domain>/README.md` exists and accurately describes the domain
- [ ] No planning documents exist for features that are already built (should be archived)
- [ ] All files in `docs/<domain>/archive/` have the `[ARCHIVED]` header
- [ ] `docs/<domain>/archive/README.md` lists all archived documents
- [ ] Implementation docs in `docs/<domain>/implementations/` follow the naming convention

### Cross-Cutting
- [ ] `docs/README.md` links are all valid
- [ ] `docs/documentation-guidelines.md` is current
- [ ] No two documents in `docs/*/status/` describe the same feature differently
- [ ] All "Last Updated" dates are within the last 30 days (during active development)

### File Structure Verification
```
docs/
  README.md                              # Master index
  documentation-guidelines.md            # This file
  suite/
    README.md
    status/current-implementation-status.md
    implementations/
    archive/README.md
  ism/
    README.md
    status/current-implementation-status.md
    implementations/
    archive/README.md
  news/
    README.md
    status/current-implementation-status.md
    implementations/
    archive/README.md
  portfolio-intelligence/
    README.md
    status/current-implementation-status.md
    implementations/
    planning/README.md
    archive/README.md
```

---

## 9. Claude Code Guidelines

When working with this codebase, Claude Code should follow these documentation practices:

### Before Starting Work
1. **Read the relevant status document first** — `docs/<domain>/status/current-implementation-status.md`
2. **Check the domain README** — `docs/<domain>/README.md`
3. **Ignore archive folders** — Documents in `archive/` are historical and should not be used for understanding current state

### During Work
1. **Flag contradictions** — If you find a document that contradicts the status doc or the codebase, flag it immediately
2. **Don't create new status documents** — Update the existing one
3. **Don't duplicate information** — If it's already in the status doc, reference it rather than restating it

### After Completing Work
1. **Update the status document** — This is mandatory for any feature completion
2. **Create an implementation document** — For non-trivial changes
3. **Archive superseded planning docs** — Follow the archive process in Section 3
4. **Update the domain README** — If capabilities or architecture changed

### Search Priority
When searching for information about the current state of any domain:
1. `docs/<domain>/status/current-implementation-status.md` (primary source)
2. `docs/<domain>/README.md` (overview and architecture)
3. `docs/<domain>/implementations/` (historical implementation details)
4. `docs/<domain>/archive/` (last resort, historical only)

---

## 10. Review Cadence

| Activity | Frequency | Responsible |
|----------|-----------|-------------|
| Update status doc after feature completion | Every time | Developer completing the feature |
| Documentation audit (checklist above) | Monthly | Project lead |
| Review and prune archives | Quarterly | Project lead |
| Update this guidelines document | As needed | Anyone (via PR) |

---

**Remember**: The goal is not to write more documentation. The goal is to have **one reliable place** to understand the current state of each domain. Everything else supports that goal.
