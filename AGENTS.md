# AGENTS.md

Instructions for AI agents working on this project.

---

## On Every Session Start

Read these files before doing anything:

1. `docs/concept.md` — project goals, architecture, design principles
2. `docs/specs.md` — file-by-file specification of what to build
3. `docs/tasks.md` — task plan with current progress

Do not make assumptions about what has been built. Check the actual files.

---

## Working on Tasks

- Pick the next unchecked task in `docs/tasks.md`, working top to bottom
- Complete one task fully before moving to the next
- After completing a task, mark it done by changing `- [ ]` to `- [x]` **immediately** — do not wait until the end of the session to mark multiple tasks at once
- If a task is partially done or blocked, add a short note inline:
  ```
  - [ ] **3.2** Integrate local VLM — blocked: model path not configured
  ```

---

## Updating `docs/tasks.md`

Only two edits are valid:
- Mark a task complete: `- [ ]` → `- [x]`
- Add a short inline note to a blocked or partial task

Do not rewrite, reorder, or remove tasks. If new tasks are needed, append them to the relevant phase or add a new phase at the bottom.

---

## Code Conventions

- Match the style of existing files before introducing new patterns
- All modules import config from `config.py` — do not hardcode paths or constants
- All DB access goes through `database.py` — do not open raw SQLite connections elsewhere
- Keep each script focused on its single responsibility per `docs/specs.md`

---

## Python Environment

This project uses a `.venv` virtual environment. Always run Python via:

```
.venv/bin/python
```

Do not use the system `python` or `python3`. Do not use `pip` directly — use `.venv/bin/pip` if package installation is needed.

---

## Verification

After implementing a task:
- Run the affected script or relevant code path to confirm it works
- For DB changes, verify schema with a fresh database file
- For the review UI, confirm keyboard shortcuts and DB state after each action

---

## File Reference

| File | Purpose |
|---|---|
| `docs/concept.md` | Source of truth for intent and design decisions |
| `docs/specs.md` | Source of truth for what each file should do |
| `docs/tasks.md` | Source of truth for progress tracking |
| `config.py` | Shared constants — edit here, not inline |
| `database.py` | All schema and DB access |
