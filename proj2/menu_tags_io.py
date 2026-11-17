"""
Export the menu to a CSV for tagging, and import the tagged CSV back with validation.

Covers every tag column: diet_tags (hard rules, see proj2.dietary) and the descriptive
tags in proj2.meal_tags (cuisine, protein, flavor, meal_type, carb_base, ...).

Typical use (see scripts/menu_tags.py):
    1. export   -> menu_tags.csv with itm_id, restaurant, name, description, allergens
                   and one column per tag kind
    2. a person fills in the tag columns (comma-separated, e.g. "vegan, gluten-free")
    3. import   -> a dry run listing every change and every problem
    4. import --apply -> writes all changes in one transaction, or nothing if any row is wrong

Only itm_id and the tag columns are read on import; the other columns are there to help
the person tagging. A CSV may carry just some tag columns: the ones it leaves out are not
touched. Items missing from the CSV are left as they are; an empty cell clears that tag.
"""

import csv
from dataclasses import dataclass, field

from proj2 import meal_tags
from proj2.dietary import DIET_TAGS_COLUMN, KNOWN_DIETS, normalize_tag, satisfied_diets

## Every column this tool reads and writes, in CSV order
TAG_COLUMNS = (DIET_TAGS_COLUMN, *meal_tags.TAG_COLUMNS)
CONTEXT_COLUMNS = ("itm_id", "restaurant", "name", "description", "allergens")
EXPORT_COLUMNS = (*CONTEXT_COLUMNS, *TAG_COLUMNS)

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

_MEAT = {"chicken", "turkey", "beef", "pork", "lamb", "goat"}

## A diet that cannot hold if the item's protein tags include one of these
PROTEIN_CONTRADICTIONS = {
    "vegetarian": _MEAT | {"fish", "shellfish"},
    "vegan": _MEAT | {"fish", "shellfish", "egg", "dairy"},
    "pescatarian": _MEAT,
    "halal": {"pork"},
    "kosher": {"pork", "shellfish"},
}

## A diet that cannot hold if the item's contains tags include one of these
CONTAINS_CONTRADICTIONS = {"halal": {"alcohol"}}


@dataclass
class ImportPlan:
    """The result of checking a CSV: changes to make, or errors that block the import."""

    changes: list = field(default_factory=list)  # (itm_id, name, column, old, new)
    columns: tuple = ()  # the tag columns the CSV carries
    unchanged: int = 0  # items whose tags all stay the same
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


def canonical_cell(column: str, raw):
    """
    Normalizes any tag cell and checks it against its column's vocabulary

    Args:
        column (str): One of TAG_COLUMNS
        raw (str | None): The cell as typed

    Returns:
        Tuple[str, List[str]]: The stored form and a list of problems (empty if valid)
    """
    if column == DIET_TAGS_COLUMN:
        stored, unknown = canonical_tags(raw)
        problems = []
        if unknown:
            problems.append(
                f"unknown tag(s) {', '.join(unknown)}; use {', '.join(sorted(KNOWN_DIETS))}"
            )
        return stored, problems
    return meal_tags.canonical(column, raw)


def contradictions(diet_tags: str, allergens: str, protein: str = None, contains: str = None):
    """
    Lists diets an item claims that its own allergens, protein or contains tags rule out

    Args:
        diet_tags (str): The item's canonical diet tags
        allergens (str | None): The item's comma-separated allergens
        protein (str | None): The item's canonical protein tags
        contains (str | None): The item's canonical contains tags (caffeine, alcohol)

    Returns:
        List[str]: Messages such as "vegan but contains dairy"; empty if consistent
    """
    declared = {tag.strip().casefold() for tag in (allergens or "").split(",") if tag.strip()}
    proteins = meal_tags.parse_tags("protein", protein)
    contained = meal_tags.parse_tags("contains", contains)
    problems = []
    for diet in sorted(satisfied_diets(diet_tags)):
        clash = sorted(declared & CONTRADICTIONS.get(diet, set()))
        if clash:
            problems.append(f"{diet} but contains {', '.join(clash)}")
        clash = sorted(proteins & PROTEIN_CONTRADICTIONS.get(diet, set()))
        if clash:
            problems.append(f"{diet} but its protein is {', '.join(clash)}")
        clash = sorted(contained & CONTAINS_CONTRADICTIONS.get(diet, set()))
        if clash:
            problems.append(f"{diet} but contains {', '.join(clash)}")
    return problems


def _column_or_null(conn, column: str, prefix: str = "") -> str:
    """A SELECT expression for a tag column, or NULL on databases that lack it."""
    return f"{prefix}{column}" if meal_tags.has_column(conn, column) else "NULL"


def _catalog(conn) -> dict:
    """itm_id -> {name, allergens, <each tag column>} for every menu item."""
    tags = ", ".join(_column_or_null(conn, column) for column in TAG_COLUMNS)
    rows = conn.execute(f'SELECT itm_id, name, allergens, {tags} FROM "MenuItem"').fetchall()
    catalog = {}
    for row in rows:
        item = {"name": row[1], "allergens": row[2]}
        # "" for untagged; 0 is a real value for levels and flags
        item.update(
            {
                column: "" if row[3 + i] is None else row[3 + i]
                for i, column in enumerate(TAG_COLUMNS)
            }
        )
        catalog[row[0]] = item
    return catalog


def export_csv(conn, out) -> int:
    """
    Writes every menu item to a CSV ready for tagging

    Args:
        conn (sqlite3.Connection): An open database connection
        out (TextIO): Where to write the CSV

    Returns:
        int: The number of items written
    """
    tags = ", ".join(_column_or_null(conn, column, "m.") for column in TAG_COLUMNS)
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
    items, unknown tags, and diets that the item's own allergens or protein contradict.
    Contradictions are checked on the item as it would be after the import, so a CSV
    with only a protein column is still checked against the stored diet tags.

    Args:
        conn (sqlite3.Connection): An open database connection
        csv_file (TextIO): The CSV, with itm_id and at least one of TAG_COLUMNS

    Returns:
        ImportPlan: The changes to make, or the errors that block the import
    """
    plan = ImportPlan()
    reader = csv.DictReader(csv_file)
    header = [name.strip() for name in (reader.fieldnames or [])]
    plan.columns = tuple(column for column in TAG_COLUMNS if column in header)
    if "itm_id" not in header or not plan.columns:
        missing = [] if "itm_id" in header else ["itm_id"]
        if not plan.columns:
            missing.append(f"at least one of {', '.join(TAG_COLUMNS)}")
        plan.errors.append(f"line 1: missing column(s) {'; '.join(missing)}")
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

        item = catalog[itm_id]
        after = dict(item)
        valid = True
        for column in plan.columns:
            new, problems = canonical_cell(column, row.get(column))
            for problem in problems:
                plan.errors.append(f"line {line}: {item['name']} has {problem}")
            valid = valid and not problems
            after[column] = new
        if not valid:
            continue
        for problem in contradictions(
            after[DIET_TAGS_COLUMN], item["allergens"], after["protein"], after["contains"]
        ) + meal_tags.tag_clashes(after):
            plan.errors.append(f"line {line}: {item['name']} is tagged {problem}")

        changed = [column for column in plan.columns if after[column] != item[column]]
        if not changed:
            plan.unchanged += 1
        for column in changed:
            plan.changes.append((itm_id, item["name"], column, item[column], after[column]))
    return plan


def apply_import(conn, plan: ImportPlan) -> int:
    """
    Writes a checked plan in one transaction, adding missing tag columns first

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
    meal_tags.ensure_columns(conn, plan.columns)
    with conn:
        for column in plan.columns:  # names come from TAG_COLUMNS, never from the CSV
            conn.executemany(
                f'UPDATE "MenuItem" SET {column} = ? WHERE itm_id = ?',
                [
                    (None if new == "" else new, itm_id)
                    for itm_id, _, changed, _, new in plan.changes
                    if changed == column
                ],
            )
    return len({itm_id for itm_id, *_ in plan.changes})
