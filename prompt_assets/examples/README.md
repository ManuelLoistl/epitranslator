# Worked examples (drop-in)

Each example is one **before → after** translation pair that shows the model
exactly what a correct translation into your target schema looks like. These are
the single highest-value ingredient in the whole tool — one complete, correct
pair teaches more than paragraphs of instructions.

## How to add an example

Create a subdirectory per example. Inside it, put two files:

```
examples/
  seir_from_r/
    source.<ext>     # the original model (any language: .R, .jl, .m, .py, ...)
    target.py        # the exact translated output in your target schema
  dengue_from_matlab/
    source.m
    target.py
```

The backend pairs `source.*` with `target.py` in each subdirectory and injects
them into the system prompt under a "WORKED EXAMPLES" heading. The file
extension of `source.*` is used to tell the model the source language.

Add as many pairs as you like (covering different source languages / model
types). Delete this README once you have real examples — it is ignored either
way.
