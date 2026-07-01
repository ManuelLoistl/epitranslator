# Design — disease category picker (roadmap item #1)

**Date:** 2026-07-01. **Status:** approved design, pending implementation plan.

## Problem / goal

On submit, let the user optionally pick a **disease category** (by transmission
route) that is fed into the translation prompt as a disambiguation hint, so an
ambiguous source translates in a category-aware way (e.g. "waterborne" nudges
toward an environmental reservoir compartment; "vector-borne" toward a vector
compartment). Optional — a default of "Unspecified" adds no hint.

The target schema defines **no** category taxonomy (`set_model_info(disease_type,
…)` is a free-form string), so the list is ours to define. The design keeps a
single source of truth so the UI dropdown and the prompt can't drift (roadmap
open-question #3).

Non-goals: persisting/"storing" the category with the output (that's roadmap #7);
feeding the category into the report call; a per-category prompt variant.

## The category list (single source of truth)

`backend/categories.py` holds the one list — each entry `{id, label, hint}`:

| id | label | hint (fed to prompt, or None) |
|----|-------|------|
| `unspecified` | Unspecified | None (default; no hint) |
| `respiratory` | Respiratory / airborne | a respiratory/airborne, person-to-person disease |
| `direct_contact` | Direct contact | a directly-contact-transmitted disease |
| `vector_borne` | Vector-borne | a vector-borne disease (e.g. mosquito/tick) |
| `waterborne` | Waterborne / environmental | a waterborne/environmental disease (may involve a reservoir) |
| `sexually_transmitted` | Sexually transmitted | a sexually transmitted disease |
| `zoonotic` | Zoonotic / spillover | a zoonotic disease with animal-reservoir spillover |

## Wiring / data flow

1. **`backend/categories.py`** — `CATEGORIES` list + a helper `hint_for(id) -> str
   | None` (returns None for `unspecified`, unknown ids, or None). `Unspecified`
   is first (the default).
2. **`backend/app.py` `/api/health`** — add `categories: [{id, label}]` (labels
   only; hints stay server-side) so the UI has one authoritative list.
3. **`static/index.html`** — a `<select id="category">` in the source pane header
   next to the language box, populated from `/api/health` `categories` on load
   (Unspecified selected by default). The selected `id` is included in the
   `/api/translate` POST body as `category`.
4. **`backend/app.py` `translate()`** — read `category` from the payload; pass it
   to `translator.stream_translation(source_code, source_language, category)`.
5. **`backend/translator.py` `stream_translation(...)`** — accept `category` and
   pass it through to `build_user_message`.
6. **`backend/prompt.py` `build_user_message(source_code, source_language,
   category)`** — when `hint_for(category)` is not None, append ONE line.

## The hint wording (must not fabricate structure)

The category is a disambiguation nudge, not a directive. The appended line
(user message, not the cached system prompt — preserves prompt caching):

> `Disease category hint: this is {hint}. Use this only to disambiguate genuinely
> ambiguous cases; the source code is authoritative — do not add compartments,
> parameters, or mechanisms the source does not contain.`

This keeps the picker from re-introducing invented structure.

## Error handling / edge cases

- Missing/empty/unknown `category` in the payload → treated as `unspecified` → no
  hint. Never errors.
- `/api/health` failing on the client → the dropdown is simply empty/absent; the
  app still translates (category omitted). Graceful degradation.

## Testing

- **`backend/categories.py`**: ids are unique; `unspecified` is first and its
  hint is None; `hint_for("unspecified") is None`; `hint_for("waterborne")` is a
  non-empty string; `hint_for("nope") is None`.
- **`build_user_message`**: with a real category the hint line is appended and
  contains the hint text; with `unspecified`/`None`/unknown, no hint line is
  added (output identical to the no-category message).
- **`/api/health`**: response includes `categories` with `unspecified` first and
  each entry having `id` + `label` (no `hint`).
- **UI (manual)**: dropdown populates from health with Unspecified default; a
  chosen category is sent in the POST body; translation works with and without a
  selection; existing report drawer unaffected.

## Wiring checklist (every new symbol has a reader)

| Introduced | Wired in |
|---|---|
| `backend/categories.py` (`CATEGORIES`, `hint_for`) | read by `app.py` health + `prompt.py` build_user_message |
| `category` request field | sent by `static/index.html`; read by `app.py translate()` |
| `stream_translation(..., category)` param | passed from `app.py`; consumed by `build_user_message` |
| `/api/health` `categories` field | rendered into the `<select>` by `static/index.html` |

## Docs to update

- `docs/ROADMAP.md`: mark item #1 shipped and note open-question #3 resolved (the
  schema has no taxonomy, so the list lives in `backend/categories.py`).
- `README.md`: one line that the source pane has an optional disease-category
  picker feeding a translation hint.
