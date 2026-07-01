## Output addendum — translation report

After the complete `model.py`, emit one line that is EXACTLY these characters
(copy it verbatim — do not paraphrase the divider, do not change the dashes to
`=`, do not add spaces):

    # ---TRANSLATION-REPORT---

then a single raw JSON object describing what the translation did. The app parses
this to show the user what needs attention and to audit every mapping. It is NOT
part of `model.py` and the user never sees it as code.

**This is machine-read, not a human comment block. Critical format rules:**
- The sentinel line must be exactly `# ---TRANSLATION-REPORT---` on its own line.
- Everything after it is **raw JSON only** — starts with `{` and ends with `}`.
- Do **NOT** write the report as Python comments. Do **NOT** prefix report lines
  with `#`. Do **NOT** wrap it in ``` code fences. Do **NOT** add prose before or
  after the JSON.
- If you catch yourself writing `# - ...` bullet lines, STOP — that is wrong;
  put that information inside the JSON `note`/`detail` fields instead.

Shape:

    {
      "attention": [
        {"severity": "high|info", "category": "...", "title": "...", "detail": "..."}
      ],
      "compartments": [
        {"schema_id": "...", "source_name": "... or null", "origin": "...", "note": "..."}
      ],
      "parameters": [
        {"schema_name": "...", "source_name": "... or null", "value": <number or string>,
         "unit": "...", "origin": "...", "note": "..."}
      ],
      "interventions": [
        {"schema_id": "...", "source_name": "... or null", "target_rates": ["..."],
         "origin": "...", "note": "..."}
      ]
    }

Rules:
- List EVERY declared compartment, parameter/edge rate, and intervention — a
  complete audit, not only the noteworthy ones.
- `origin` is one of:
  - "source"    — taken directly from the source model.
  - "converted" — same quantity, unit-transformed (period↔rate, %↔fraction).
  - "derived"   — computed or restructured from the source (e.g. beta from R0, or
                  a compartment split for a competing-risks branch).
  - "guessed"   — NOT in the source; invented as a plausible default.
  (Compartments use source/derived/guessed; interventions use source/guessed.)
- `source_name` is the name in the source, or null if it has no counterpart.
- `note` is a short (<= ~15 word) explanation; use "" when there is nothing to add.
- `attention` flags what the user should review. `severity` is "high" (could be
  wrong / needs a human decision) or "info" (a faithful simplification worth
  knowing). `category` is one of:
  - "no_dynamics"       — the source contained no model dynamics (e.g. a run
                          wrapper); compartments/rates were INFERRED, not
                          translated. Always "high"; say so plainly.
  - "invented"          — one or more guessed compartments/parameters/interventions.
  - "dropped_structure" — structure simplified away (age, stochasticity, spatial
                          coupling, non-exponential delays, interventions).
  - "model_mismatch"    — the source is a different model class (agent-based,
                          inference, state-space) reduced to a compartmental core.
  - "ambiguity"         — a genuine interpretation choice was made.
- Always emit the report block. `attention` may be []. Emit valid JSON: double
  quotes, no trailing commas, no comments.

Example (abbreviated):

    # ---TRANSLATION-REPORT---
    {"attention":[{"severity":"info","category":"dropped_structure","title":"Deterministic reduction","detail":"Source was stochastic; rendered as an ODE."}],"compartments":[{"schema_id":"S","source_name":"S","origin":"source","note":""},{"schema_id":"I","source_name":"I","origin":"source","note":""},{"schema_id":"R","source_name":"R","origin":"source","note":""}],"parameters":[{"schema_name":"beta","source_name":"b","value":0.1,"unit":"per day","origin":"source","note":""},{"schema_name":"gamma","source_name":"g","value":0.05,"unit":"per day","origin":"source","note":""}],"interventions":[]}
