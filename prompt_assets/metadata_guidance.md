## Recording provenance with `set_model_metadata`

The source often carries provenance the schema can hold: an author header, a
license line, a paper DOI, a stated assumption, a documented limitation. When it
does, call `schema.set_model_metadata(...)` in `define_parameters()` right after
`set_model_info(...)` and pass only the fields the source actually supports:

```python
schema.set_model_metadata(
    authors=[{"name": "A. Researcher", "affiliation": "Example University"}],
    license="MIT",
    citations=["https://doi.org/10.1000/example"],
    key_assumptions=["Well-mixed population", "No waning immunity"],
)
```

The call is optional and artifact-only — it never changes the simulation.

**Do not invent metadata.** Omit a field rather than guess at it: no inferred
authors, no assumed license, no fabricated citations, no assumptions the source
does not state. If the source carries no provenance at all, omit the call
entirely. `key_assumptions` may restate an assumption the source makes
explicitly (in prose, comments, or structure) — it is not a place to editorialise
about the model.
