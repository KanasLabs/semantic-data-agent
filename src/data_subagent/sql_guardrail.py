from __future__ import annotations

import re

BANNED_KEYWORDS = {
    "alter",
    "attach",
    "copy",
    "create",
    "delete",
    "detach",
    "drop",
    "grant",
    "insert",
    "merge",
    "replace",
    "revoke",
    "truncate",
    "update",
}


class SQLGuardrailError(ValueError):
    pass


def validate_readonly_sql(sql: str) -> str:
    normalized = sql.strip()
    if not normalized:
        raise SQLGuardrailError("SQL is empty.")

    without_trailing = normalized[:-1].strip() if normalized.endswith(";") else normalized
    if ";" in without_trailing:
        raise SQLGuardrailError("Only one SQL statement is allowed.")

    first_token_match = re.match(r"^\s*([a-zA-Z_]+)", without_trailing)
    first_token = first_token_match.group(1).lower() if first_token_match else ""
    if first_token not in {"select", "with"}:
        raise SQLGuardrailError("Only SELECT/WITH queries are allowed.")

    tokens = {token.lower() for token in re.findall(r"\b[a-zA-Z_]+\b", without_trailing)}
    dangerous = sorted(tokens & BANNED_KEYWORDS)
    if dangerous:
        raise SQLGuardrailError(f"Read-only guardrail rejected keyword(s): {', '.join(dangerous)}.")

    return without_trailing
