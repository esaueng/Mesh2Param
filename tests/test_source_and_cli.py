from __future__ import annotations

import ast

import pytest
from mesh2param.cli import main
from mesh2param.samples import sample_graph
from mesh2param.source import generate_cadquery_source


def test_generated_cadquery_source_is_deterministic_and_data_only() -> None:
    graph = sample_graph("block-through-hole")
    first = generate_cadquery_source(graph)
    second = generate_cadquery_source(graph)
    assert first == second
    assert "# feature 0: feature.base (extrusion)" in first
    assert "# feature 1: feature.hole (hole)" in first
    assert "subprocess" not in first
    assert "eval(" not in first
    assert "exec(" not in first
    tree = ast.parse(first)
    imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        (node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert imports == {"cadquery", "mesh2param", "mesh2param_contracts"}


def test_cli_help_and_sample_listing(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "reconstruct" in output
    assert "rebuild" in output
    assert main(["samples", "list"]) == 0
    output = capsys.readouterr().out
    assert "rectangular-block" in output
    assert "stepped-turned-part" in output
    assert len(output.strip().splitlines()) == 10
