"""
db_source.py — Parse init.sql to extract product data from catalog.products.

Reads INSERT INTO catalog.products statements and returns a list of product
dicts with keys: id, name, description, price_currency_code, price_units,
price_nanos, categories.
"""

from __future__ import annotations

import re
from pathlib import Path


def load_products_from_sql(sql_file_path: str) -> list[dict]:
    """Parse INSERT INTO catalog.products rows from an init.sql file.

    Args:
        sql_file_path: Absolute or relative path to the SQL file.

    Returns:
        A list of product dicts.  Each dict has keys:
        id, name, description, picture, price_currency_code,
        price_units (int), price_nanos (int), categories (list[str]).

    Raises:
        FileNotFoundError: If sql_file_path does not exist.
        ValueError: If parsing fails or produces 0 products.
    """
    path = Path(sql_file_path)
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {sql_file_path}")

    sql_text = path.read_text(encoding="utf-8")

    # ------------------------------------------------------------------ #
    # 1. Locate the INSERT block for catalog.products                     #
    # ------------------------------------------------------------------ #
    # The INSERT spans from "INSERT INTO catalog.products …" up to the
    # terminating semicolon.  We grab the whole statement.
    insert_pattern = re.compile(
        r"INSERT\s+INTO\s+catalog\.products\s*"
        r"\([^)]+\)\s*VALUES\s*(.+?);",
        re.DOTALL | re.IGNORECASE,
    )
    m = insert_pattern.search(sql_text)
    if not m:
        raise ValueError(
            "Could not locate INSERT INTO catalog.products in the SQL file."
        )

    values_block = m.group(1)

    # ------------------------------------------------------------------ #
    # 2. Split the block into individual row tuples                       #
    # ------------------------------------------------------------------ #
    # Each row is wrapped in parentheses: ('...', '...', ...).
    # We find each balanced (...) group.  A simple approach: match from
    # an opening '(' to the first unquoted ')'.
    #
    # Strategy: walk character-by-character to handle escaped quotes
    # (PostgreSQL doubles them: '').
    rows: list[str] = []
    i = 0
    while i < len(values_block):
        if values_block[i] == "(":
            depth = 0
            start = i
            in_string = False
            while i < len(values_block):
                ch = values_block[i]
                if in_string:
                    if ch == "'" and i + 1 < len(values_block) and values_block[i + 1] == "'":
                        i += 2  # skip escaped quote
                        continue
                    if ch == "'":
                        in_string = False
                else:
                    if ch == "'":
                        in_string = True
                    elif ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                        if depth == 0:
                            rows.append(values_block[start + 1 : i])  # inside parens
                            i += 1
                            break
                i += 1
        else:
            i += 1

    if not rows:
        raise ValueError(
            "Parsed 0 row tuples from INSERT INTO catalog.products."
        )

    # ------------------------------------------------------------------ #
    # 3. Parse each row into a product dict                               #
    # ------------------------------------------------------------------ #
    # Column order (from the INSERT):
    #   id, name, description, picture, price_currency_code,
    #   price_units, price_nanos, categories
    products: list[dict] = []
    for row_str in rows:
        fields = _split_sql_row(row_str)
        if len(fields) != 8:
            raise ValueError(
                f"Expected 8 fields per row, got {len(fields)}: {row_str[:120]}…"
            )

        product = {
            "id": _unquote(fields[0]),
            "name": _unquote(fields[1]),
            "description": _unquote(fields[2]),
            "picture": _unquote(fields[3]),
            "price_currency_code": _unquote(fields[4]),
            "price_units": int(fields[5].strip()),
            "price_nanos": int(fields[6].strip()),
            "categories": [
                c.strip() for c in _unquote(fields[7]).split(",") if c.strip()
            ],
        }
        products.append(product)

    if not products:
        raise ValueError("Parsing produced 0 products — check the SQL file.")

    return products


# ------------------------------------------------------------------ #
# Internal helpers                                                    #
# ------------------------------------------------------------------ #


def _split_sql_row(row: str) -> list[str]:
    """Split a comma-separated SQL values row respecting quoted strings.

    Handles PostgreSQL-style doubled single-quote escaping ('').
    Returns raw token strings (still quoted for string values).
    """
    tokens: list[str] = []
    current: list[str] = []
    in_string = False
    i = 0
    while i < len(row):
        ch = row[i]
        if in_string:
            if ch == "'" and i + 1 < len(row) and row[i + 1] == "'":
                current.append("''")
                i += 2
                continue
            if ch == "'":
                current.append(ch)
                in_string = False
            else:
                current.append(ch)
        else:
            if ch == "'":
                current.append(ch)
                in_string = True
            elif ch == ",":
                tokens.append("".join(current))
                current = []
            else:
                current.append(ch)
        i += 1
    tokens.append("".join(current))
    return tokens


def _unquote(value: str) -> str:
    """Remove surrounding single quotes and unescape doubled quotes."""
    v = value.strip()
    if v.startswith("'") and v.endswith("'"):
        v = v[1:-1]
    return v.replace("''", "'")
