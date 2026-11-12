"""
Export the menu to a CSV for tagging, and import the tagged CSV back with validation.

Typical use (see scripts/diet_tags.py):
    1. export   -> menu_tags.csv with itm_id, restaurant, name, description, allergens, diet_tags
    2. a person fills in the diet_tags column (comma-separated, e.g. "vegan, gluten-free")
    3. import   -> a dry run listing every change and every problem
    4. import --apply -> writes all changes in one transaction, or nothing if any row is wrong

Only itm_id and diet_tags are read on import; the other columns are there to help the
person tagging. Items missing from the CSV are left as they are; a row with an empty
diet_tags clears that item's tags.
"""

import csv
from dataclasses import dataclass, field

from proj2.dietary import (
    DIET_TAGS_COLUMN,
    KNOWN_DIETS,
    ensure_diet_tags_column,
    has_diet_tags_column,
    normalize_tag,
    satisfied_diets,
)

EXPORT_COLUMNS = ("itm_id", "restaurant", "name", "description", "allergens", "diet_tags")
REQUIRED_COLUMNS = ("itm_id", "diet_tags")

## A diet that cannot hold if the item declares one of these allergens.
## Each entry lists the allergen spellings that count (compared casefolded).
CONTRADICTIONS = {
    "vegetarian": {"fish", "shellfish", "crustacean", "shrimp", "meat", "pork", "beef"},
    "vegan": {"dairy", "milk", "eggs", "egg", "honey"},
    "pescatarian": {"meat", "pork", "beef"},
    "gluten-free": {"gluten", "wheat"},
    "halal": {"pork", "alcohol"},
    "kosher": {"pork", "shellfish", "crustacean", "shrimp"},
}


@dataclass
class ImportPlan:
    """The result of checking a CSV: changes to make, or errors that block the import."""

    changes: list = field(default_factory=list)  # (itm_id, name, old_tags, new_tags)
    unchanged: int = 0
    errors: list = field(default_factory=list)  # "line N: message"

    @property
    def ok(self) -> bool:
        return not self.errors


def canonical_tags(raw: str):
    """
    Normalizes a diet_tags cell

    Args:
        raw (str): The cell as typed, e.g. "Vegan,  Gluten Free"

    Returns:
        Tuple[str, List[str]]: The stored form (sorted, de-duplicated, e.g. "gluten-free, vegan")
            and any tags that are not in KNOWN_DIETS
    """
    tags = {normalize_tag(tag) for tag in (raw or "").split(",") if tag.strip()}
    unknown = sorted(tags - KNOWN_DIETS)
    return ", ".join(sorted(tags & KNOWN_DIETS)), unknown


def contradictions(diet_tags: str, allergens: str) -> list:
    """
    Lists diets an item claims that its own allergen list rules out

    Args:
        diet_tags (str): The item's canonical diet tags
        allergens (str | None): The item's comma-separated allergens

    Returns:
        List[str]: Messages such as "vegan but contains dairy"; empty if consistent
    """
    declared = {tag.strip().casefold() for tag in (allergens or "").split(",") if tag.strip()}
    problems = []
    for diet in sorted(satisfied_diets(diet_tags)):
        clash = sorted(declared & CONTRADICTIONS.get(diet, set()))
        if clash:
            problems.append(f"{diet} but contains {', '.join(clash)}")
    return problems


def _catalog(conn) -> dict:
    """itm_id -> (name, allergens, current diet_tags) for every menu item."""
    tags = DIET_TAGS_COLUMN if has_diet_tags_column(conn) else "NULL"
    rows = conn.execute(f'SELECT itm_id, name, allergens, {tags} FROM "MenuItem"').fetchall()
    return {row[0]: (row[1], row[2], row[3] or "") for row in rows}


def export_csv(conn, out) -> int:
    """
    Writes every menu item to a CSV ready for tagging

    Args:
        conn (sqlite3.Connection): An open database connection
        out (TextIO): Where to write the CSV

    Returns:
        int: The number of items written
    """
    tags = f"m.{DIET_TAGS_COLUMN}" if has_diet_tags_column(conn) else "NULL"
    rows = conn.execute(
        f"""
        SELECT m.itm_id, COALESCE(r.name, ''), m.name, m.description, m.allergens, {tags}
        FROM "MenuItem" m LEFT JOIN "Restaurant" r ON r.rtr_id = m.rtr_id
        ORDER BY r.name, m.itm_id
        """
    ).fetchall()
    writer = csv.writer(out)
    writer.writerow(EXPORT_COLUMNS)
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    return len(rows)


def plan_import(conn, csv_file) -> ImportPlan:
    """
    Checks a tagged CSV against the database without changing anything

    Every problem is reported, not just the first: unknown or missing item IDs, repeated
    items, unknown tags, and diets that the item's own allergens contradict.

    Args:
        conn (sqlite3.Connection): An open database connection
        csv_file (TextIO): The CSV, with at least itm_id and diet_tags columns

    Returns:
        ImportPlan: The changes to make, or the errors that block the import
    """
    plan = ImportPlan()
    reader = csv.DictReader(csv_file)
    header = [name.strip() for name in (reader.fieldnames or [])]
    missing = [name for name in REQUIRED_COLUMNS if name not in header]
    if missing:
        plan.errors.append(f"line 1: missing column(s) {', '.join(missing)}")
        return plan
    reader.fieldnames = header

    catalog = _catalog(conn)
    seen = {}
    for line, row in enumerate(reader, start=2):
        raw_id = (row.get("itm_id") or "").strip()
        extra = row.pop(None, None)  # cells past the last header column
        if not raw_id and not extra and not any((v or "").strip() for v in row.values()):
            continue  # blank line
        if extra:
            plan.errors.append(
                f"line {line}: more cells than columns; put several tags in quotes, "
                f'e.g. "vegan, halal"'
            )
            continue
        try:
            itm_id = int(raw_id)
        except ValueError:
            plan.errors.append(f"line {line}: itm_id {raw_id!r} is not a number")
            continue
        if itm_id not in catalog:
            plan.errors.append(f"line {line}: there is no menu item {itm_id}")
            continue
        if itm_id in seen:
            plan.errors.append(f"line {line}: item {itm_id} already appears on line {seen[itm_id]}")
            continue
        seen[itm_id] = line

        name, allergens, current = catalog[itm_id]
        new, unknown = canonical_tags(row.get("diet_tags"))
        if unknown:
            plan.errors.append(
                f"line {line}: {name} has unknown tag(s) {', '.join(unknown)}; "
                f"use {', '.join(sorted(KNOWN_DIETS))}"
            )
            continue
        for problem in contradictions(new, allergens):
            plan.errors.append(f"line {line}: {name} is tagged {problem}")
        if new == current:
            plan.unchanged += 1
        else:
            plan.changes.append((itm_id, name, current, new))
    return plan


def apply_import(conn, plan: ImportPlan) -> int:
    """
    Writes a checked plan in one transaction, adding the diet_tags column if needed

    Args:
        conn (sqlite3.Connection): An open database connection
        plan (ImportPlan): A plan from plan_import with no errors

    Returns:
        int: The number of items updated

    Raises:
        ValueError: if the plan has errors
    """
    if not plan.ok:
        raise ValueError("Refusing to import a CSV with errors.")
    ensure_diet_tags_column(conn)
    with conn:
        conn.executemany(
            f'UPDATE "MenuItem" SET {DIET_TAGS_COLUMN} = ? WHERE itm_id = ?',
            [(new or None, itm_id) for itm_id, _, _, new in plan.changes],
        )
    return len(plan.changes)
