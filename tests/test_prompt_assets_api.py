"""Guards the prompt assets against Pandemic Simulator API drift.

The assembled system prompt teaches Claude an API surface. When the framework
renames or removes part of that surface, every translation we emit stops
building — silently, because the app never imports the framework. These tests
pin the names the framework actually exposes at upstream 3e28faa (2026-08-10).

When upstream renames something again, update BOTH the assets and this file.
"""
import ast
from pathlib import Path

from backend.prompt import build_system_prompt

ASSETS = Path(__file__).resolve().parent.parent / "prompt_assets"
EXAMPLES = sorted(ASSETS.glob("examples/*/target.py"))

# Framework names that no longer exist. None may appear anywhere in the prompt.
RETIRED = ["derivative(", "_compute_derivatives", "set_travel_volume"]


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
    for path in EXAMPLES:
        text = path.read_text(encoding="utf-8")
        assert "self.travel_matrix =" not in text, (
            f"{path.parent.name}: the framework owns self.travel_matrix"
        )
