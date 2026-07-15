"""Compile per-step artifacts into a single spec.md (ordered by pipeline)."""
from __future__ import annotations

from . import steps


def assemble_spec(slug: str, version: str, artifacts: dict[str, str]) -> str:
    parts: list[str] = [f"# {slug} — Product Spec", ""]
    parts.append(f"_Сгенерировано ботом launch-11 (пайплайн Сейсембая, версия: {version})._")
    parts.append("")
    for step in steps.PIPELINES.get(version, []):
        body = artifacts.get(step.id)
        if not body:
            continue  # skip missing steps gracefully
        parts.append(f"## {step.id}. {step.title}")
        parts.append("")
        parts.append(body.strip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"
