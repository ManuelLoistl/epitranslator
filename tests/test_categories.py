from backend.categories import CATEGORIES, hint_for, public_categories


def test_ids_unique_and_unspecified_first():
    ids = [c["id"] for c in CATEGORIES]
    assert len(ids) == len(set(ids))
    assert ids[0] == "unspecified"


def test_unspecified_has_no_hint():
    assert CATEGORIES[0]["hint"] is None
    assert hint_for("unspecified") is None


def test_hint_for_known_category():
    h = hint_for("waterborne")
    assert isinstance(h, str) and h.strip()


def test_hint_for_unknown_or_none():
    assert hint_for("nope") is None
    assert hint_for(None) is None
    assert hint_for("") is None


def test_public_categories_omit_hint_and_keep_order():
    pub = public_categories()
    assert pub[0] == {"id": "unspecified", "label": "Unspecified"}
    assert all(set(c.keys()) == {"id", "label"} for c in pub)
    assert len(pub) == len(CATEGORIES)
