"""Guards the prompt assets against Pandemic Simulator API drift.

The assembled system prompt teaches Claude an API surface. When the framework
renames or removes part of that surface, every translation we emit stops
building — silently, because the app never imports the framework. These tests
pin the names the framework actually exposes at upstream 699afe6 (2026-08-14).

When upstream renames something again, update BOTH the assets and this file.
"""
import ast
from pathlib import Path

from backend.prompt import build_system_prompt

ASSETS = Path(__file__).resolve().parent.parent / "prompt_assets"
EXAMPLES = sorted(ASSETS.glob("examples/*/target.py"))

# Framework names that no longer exist — plus add_disease_parameter, which
# upstream renamed to add_parameter at 3594940 (a deprecated alias remains,
# but the prompt must teach the canonical name). None may appear in the prompt.
RETIRED = ["derivative(", "_compute_derivatives", "set_travel_volume",
           "add_disease_parameter"]


def test_examples_exist():
    assert EXAMPLES, "no worked examples found under prompt_assets/examples/"


def test_no_retired_framework_names_in_system_prompt():
    prompt = build_system_prompt()
    for name in RETIRED:
        assert name not in prompt, f"retired framework API in the prompt: {name}"


def test_examples_define_equation_not_derivative():
    for path in EXAMPLES:
        methods = {
            node.name
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(node, ast.FunctionDef)
        }
        assert "equation" in methods, f"{path.parent.name}: must define equation()"
        assert "derivative" not in methods, f"{path.parent.name}: derivative() was removed upstream"


def test_examples_prepare_initial_state_returns_a_bare_state_array():
    # simulation_manager.py does `init_state = model.prepare_initial_state()`.
    # Returning a tuple hands the solver a tuple where it expects the state.
    for path in EXAMPLES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        fn = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "prepare_initial_state"
        )
        returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return) and n.value is not None]
        assert returns, f"{path.parent.name}: prepare_initial_state must return the state array"
        for node in returns:
            assert not isinstance(node.value, ast.Tuple), (
                f"{path.parent.name}: prepare_initial_state must not return a tuple"
            )


def test_examples_never_assign_the_travel_matrix():
    # The framework builds self.travel_matrix via _ensure_travel_matrix() before
    # prepare_initial_state(), and _apply_interventions() stores its own result.
    # A model that travels overrides build_travel_matrix() instead.
    def _is_self_travel_matrix(node):
        return (
            isinstance(node, ast.Attribute)
            and node.attr == "travel_matrix"
            and isinstance(node.value, ast.Name)
            and node.value.id == "self"
        )

    def _assigns_self_travel_matrix(target):
        if isinstance(target, ast.Tuple):
            return any(_assigns_self_travel_matrix(elt) for elt in target.elts)
        return _is_self_travel_matrix(target)

    for path in EXAMPLES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = node.targets
            elif isinstance(node, ast.AugAssign):
                targets = [node.target]
            else:
                continue
            assert not any(_assigns_self_travel_matrix(t) for t in targets), (
                f"{path.parent.name}: the framework owns self.travel_matrix"
            )


def test_system_prompt_documents_set_model_metadata():
    prompt = build_system_prompt()
    assert "set_model_metadata" in prompt
    # A sentence from metadata_guidance.md's no-invention rule, distinctive
    # enough that it can't come from the target_schema.py stub (which only
    # has the bare method signature) -- so this only passes if the
    # metadata_guidance append block in build_system_prompt() actually ran.
    assert "Omit a field rather than guess at it" in prompt


def test_metadata_guidance_forbids_invention():
    from backend.prompt import assets_status

    # Checked against the assembled prompt, not the raw file, so a dropped
    # metadata_guidance append block fails this test too.
    prompt = build_system_prompt()
    assert "Do not invent metadata" in prompt
    assert assets_status()["metadata_guidance_present"] is True
