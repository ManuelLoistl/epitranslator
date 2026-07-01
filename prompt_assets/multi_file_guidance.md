## When multiple files are provided

When the source is provided as several files (each under a `=== file: ... ===`
header), treat them together as one model:

- The file that defines the **dynamics** is authoritative for the model
  structure (compartments and flows).
- **Parameter and data files** (e.g. a params file or a CSV) supply the numeric
  values — use those values instead of guessing defaults.
- Do **not** invent compartments, parameters, or mechanisms from a run wrapper,
  entry-point, or config file that contains no dynamics.
- A **contact matrix** conveys the age/group structure of the model: declare it
  with `add_demographic_group` (age ranges). Its exact cell values are not
  transcribed — the schema uses built-in Prem 2021 contact matrices, with
  `set_contact_override` only for specific deviations that matter.
