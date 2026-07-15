from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import yaml


def prepare_baseline(*, source_project: Path, output_project: Path, force: bool) -> dict[str, object]:
    source_project = source_project.resolve()
    output_project = output_project.resolve()
    if not (source_project / "wren_project.yml").is_file():
        raise ValueError(f"Source is not a Wren project: {source_project}")
    if output_project.exists():
        if not force:
            raise FileExistsError(f"Output already exists: {output_project}")
        shutil.rmtree(output_project)
    shutil.copytree(
        source_project,
        output_project,
        symlinks=True,
        ignore=shutil.ignore_patterns(".wren", "target", "__pycache__", "*.pyc"),
    )

    orders_path = output_project / "models" / "orders" / "metadata.yml"
    orders = yaml.safe_load(orders_path.read_text(encoding="utf-8"))
    if not isinstance(orders, dict):
        raise ValueError(f"Invalid orders model: {orders_path}")
    columns = orders.get("columns")
    if not isinstance(columns, list):
        raise ValueError(f"Orders model has no columns: {orders_path}")
    amount_column = next(
        (
            column
            for column in columns
            if isinstance(column, dict) and column.get("name") == "total_amount"
        ),
        None,
    )
    if not isinstance(amount_column, dict):
        raise ValueError("Orders model has no total_amount column.")
    properties = amount_column.setdefault("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("total_amount properties must be an object.")
    properties["description"] = (
        "Gross order amount. Currency and realized-revenue treatment require business confirmation."
    )
    orders_path.write_text(
        yaml.safe_dump(orders, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )

    rules_path = output_project / "knowledge" / "rules" / "general.md"
    rules_path.write_text(
        "# StarRocks MVP schema-level rules\n\n"
        "- The dataset is a local development fixture and contains no production data.\n"
        "- No currency or realized-revenue business policy is defined in this baseline.\n"
        "- `order_date` is the observed order date field.\n"
        "- Customer analysis may use the validated orders-to-customers relationship.\n",
        encoding="utf-8",
    )
    stale_outcome = output_project / "onboarding" / "revision_outcome.json"
    if stale_outcome.exists():
        stale_outcome.unlink()
    return {
        "ok": True,
        "source_project": str(source_project),
        "output_project": str(output_project),
        "orders_model": str(orders_path),
        "rules": str(rules_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-project",
        default="data/wren/starrocks_mvp_wren_project",
    )
    parser.add_argument(
        "--output-project",
        default="data/tmp/starrocks_revision_acceptance/base_project",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = prepare_baseline(
        source_project=Path(args.source_project),
        output_project=Path(args.output_project),
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
