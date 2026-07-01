"""The single source of truth for the disease-category picker.

Categories are by transmission route. They are a disambiguation HINT fed to the
translation prompt — never a directive to invent structure. `unspecified` (the
default, first) adds no hint.
"""
from __future__ import annotations

from typing import List, Optional

CATEGORIES: List[dict] = [
    {"id": "unspecified", "label": "Unspecified", "hint": None},
    {"id": "respiratory", "label": "Respiratory / airborne",
     "hint": "a respiratory / airborne, person-to-person disease"},
    {"id": "direct_contact", "label": "Direct contact",
     "hint": "a directly contact-transmitted disease"},
    {"id": "vector_borne", "label": "Vector-borne",
     "hint": "a vector-borne disease (e.g. mosquito- or tick-transmitted)"},
    {"id": "waterborne", "label": "Waterborne / environmental",
     "hint": "a waterborne / environmental disease (it may involve an "
             "environmental reservoir)"},
    {"id": "sexually_transmitted", "label": "Sexually transmitted",
     "hint": "a sexually transmitted disease"},
    {"id": "zoonotic", "label": "Zoonotic / spillover",
     "hint": "a zoonotic disease with animal-reservoir spillover"},
]

_HINTS = {c["id"]: c["hint"] for c in CATEGORIES}


def hint_for(category_id: Optional[str]) -> Optional[str]:
    """Return the prompt hint for a category id, or None (unspecified/unknown)."""
    if not category_id:
        return None
    return _HINTS.get(category_id)


def public_categories() -> List[dict]:
    """The {id, label} list for the UI dropdown (hints stay server-side)."""
    return [{"id": c["id"], "label": c["label"]} for c in CATEGORIES]
