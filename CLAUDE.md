# EpiTranslator — project guidance

## Prompt assets: keep the existing prompt files stable

The translation prompt is assembled at request time from files in
`prompt_assets/` (see `backend/prompt.py` → `build_system_prompt()`):
`system_prompt.md` (instructions), `target_schema.py` (the target schema), and
`examples/` (worked before/after pairs). Treat these as the **shared,
externally-owned translation prompt**.

**Rules:**

- **Avoid changing the existing prompt files** (`system_prompt.md`,
  `target_schema.py`, `examples/`) as much as possible. They *can* be changed
  when it is reasonable/necessary (e.g. fixing a genuine correctness bug), but
  keep edits minimal and clearly justified.
- **When additional prompt behavior is needed** — especially app-specific
  concerns like output formatting — **prefer adding a NEW prompt-asset file**
  that `build_system_prompt()` appends, rather than editing the existing files.
  Wire the new file in via `backend/prompt.py` (that is assembly *code*, not
  prompt content, so it does not count as changing the prompt).
- **Log every prompt change** in
  [docs/prompt-change-log.md](docs/prompt-change-log.md) — this is required for
  **any** change that affects the assembled prompt, whether editing an existing
  prompt file or adding a new appended prompt-asset file. Record the before/after
  (or, for a new file, its purpose) and the rationale, so changes can be reviewed
  and shared with the prompt's authors.

**Why:** the core prompt is meant to stay close to what its authors maintain, so
our changes can be shared upstream and we don't silently diverge from the
canonical translation prompt.
