from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_onboarding_report(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_report(result), encoding="utf-8")


def _render_report(result: dict[str, Any]) -> str:
    command_sections = []
    for name, command in result.get("wren_commands", {}).items():
        command_sections.append(
            "\n".join(
                [
                    f"### {name}",
                    "",
                    "```text",
                    f"args: {' '.join(str(part) for part in command.get('args', []))}",
                    f"returncode: {command.get('returncode')}",
                    "stdout:",
                    str(command.get("stdout") or "").strip(),
                    "stderr:",
                    str(command.get("stderr") or "").strip(),
                    "```",
                ]
            )
        )
    codex_section = _render_codex_section(result.get("codex"))

    tables = result.get("models") or []
    summary_lines = [
        f"- Status: {'OK' if result.get('ok') else 'FAILED'}",
        f"- Project name: `{result.get('project_name')}`",
        f"- Source: `{result.get('source')}`",
        f"- Wren project: `{result.get('wren_project_dir')}`",
        f"- Wren home: `{result.get('wren_home')}`",
        f"- Models: {len(tables)}",
        f"- Relationships: {result.get('relationship_count')}",
    ]
    optional_paths = (
        ("DuckDB path", result.get("duckdb_path")),
        ("Profile", result.get("profile_name")),
        ("Connection config", result.get("connection_path")),
        ("Discovery snapshot", result.get("discovery_snapshot_path")),
        ("Schema manifest", result.get("schema_manifest_path")),
        ("Query evidence", result.get("evidence_path")),
    )
    for label, value in optional_paths:
        if value:
            summary_lines.append(f"- {label}: `{value}`")
    return "\n".join(
        [
            "# Wren Context Builder Onboarding Report",
            "",
            f"Generated at: {datetime.now(timezone.utc).isoformat()}",
            "",
            "## Summary",
            "",
            "\n".join(summary_lines),
            "",
            "## Models",
            "",
            "\n".join(f"- `{name}`" for name in tables) or "- none",
            "",
            "## Wren Commands",
            "",
            "\n\n".join(command_sections) or "No Wren commands were run.",
            "",
            codex_section,
            "",
            "## Limitations",
            "",
            "- Automatically generated schema-level MDL is a draft semantic layer.",
            "- Business metrics, synonyms, field definitions, permissions, and time semantics need human or business-document input.",
            "- Relationships come from database metadata and should be reviewed before relying on relationship-driven joins.",
            "",
        ]
    )


def _render_codex_section(codex: Any) -> str:
    if not isinstance(codex, dict):
        return "## Codex Execution\n\nNo Codex execution data."
    lines = [
        "## Codex Execution",
        "",
        f"- Executed: {codex.get('executed')}",
        f"- Status: {'OK' if codex.get('ok') else 'FAILED'}",
        f"- Post validate: {codex.get('post_validate')}",
        f"- Max repair rounds: {codex.get('max_repair_rounds')}",
        f"- Repair rounds used: {codex.get('repair_rounds_used')}",
        "",
    ]
    rounds = codex.get("rounds")
    if isinstance(rounds, list) and rounds:
        lines.extend(["### Rounds", ""])
        for item in rounds:
            if not isinstance(item, dict):
                continue
            command = item.get("codex_command") if isinstance(item.get("codex_command"), dict) else {}
            lines.extend(
                [
                    f"- Round {item.get('round')} ({item.get('kind')}): "
                    f"codex_returncode={command.get('returncode')}, "
                    f"prompt=`{item.get('prompt_path')}`, "
                    f"validation=`{item.get('validation_path')}`",
                ]
            )
        lines.append("")
    final_validation = codex.get("final_validation")
    if isinstance(final_validation, dict) and final_validation:
        lines.extend(["### Final Outer Validation", ""])
        for name, command in final_validation.items():
            if not isinstance(command, dict):
                continue
            lines.extend(
                [
                    f"#### {name}",
                    "",
                    "```text",
                    f"args: {' '.join(str(part) for part in command.get('args', []))}",
                    f"returncode: {command.get('returncode')}",
                    "stdout:",
                    str(command.get("stdout") or "").strip(),
                    "stderr:",
                    str(command.get("stderr") or "").strip(),
                    "```",
                    "",
                ]
            )
    return "\n".join(lines).rstrip()
