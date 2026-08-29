from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any


def load_graph(path: str | Path) -> dict[str, list[str]]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload["dataset_lineage"] if "dataset_lineage" in payload else payload


def get_downstream_assets(graph: dict[str, list[str]], start: str) -> list[str]:
    """Return transitive downstream assets in BFS order, excluding start."""
    seen = {start}
    q: deque[str] = deque([start])
    out: list[str] = []
    while q:
        node = q.popleft()
        for child in graph.get(node, []):
            if child not in seen:
                seen.add(child)
                out.append(child)
                q.append(child)
    return out


def get_column_downstream(
    column_graph: dict[str, list[str]], start_column: str
) -> list[str]:
    """Return transitive downstream columns in BFS order, excluding start_column."""
    seen = {start_column}
    q: deque[str] = deque([start_column])
    out: list[str] = []
    while q:
        node = q.popleft()
        for child in column_graph.get(node, []):
            if child not in seen:
                seen.add(child)
                out.append(child)
                q.append(child)
    return out


def extract_dbt_dataset_graph(
    manifest_path: str | Path, *, include_tests: bool = False
) -> dict[str, list[str]]:
    """Minimal dbt manifest parser.

    It maps each dbt node unique_id to the nodes that depend on it.
    Excludes test nodes by default so downstream blast-radius reflects data assets.
    """
    path = Path(manifest_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    graph: dict[str, list[str]] = {}
    child_map = manifest.get("child_map", {})
    data_prefixes = ("model.", "seed.", "snapshot.", "source.", "exposure.")
    for parent, children in child_map.items():
        if not include_tests and not parent.startswith(data_prefixes):
            continue
        graph[parent] = [
            child for child in children if include_tests or child.startswith(data_prefixes)
        ]
    return graph



def extract_dbt_clean_graph(manifest_path: str | Path) -> dict[str, list[str]]:
    """Parses dbt manifest and returns clean human-readable model dependency graph."""
    path = Path(manifest_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    graph: dict[str, list[str]] = {}
    child_map = manifest.get("child_map", {})

    def _clean_name(unique_id: str) -> str:
        parts = unique_id.split(".")
        return parts[-1] if len(parts) > 1 else unique_id

    for parent, children in child_map.items():
        clean_p = _clean_name(parent)
        clean_children = [_clean_name(c) for c in children if not c.startswith("test.")]
        if clean_children:
            graph[clean_p] = list(set(clean_children))
    return graph

