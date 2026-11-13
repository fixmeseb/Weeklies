"""
Descriptive menu-item tags: what an item is, for judging how varied a plan is.

Each tag is its own MenuItem column. There are three kinds:

  * tags  - a comma-separated list from a closed vocabulary, like MenuItem.diet_tags
            (e.g. protein "chicken, egg"). Some take only one value (course).
  * level - a whole number in a fixed range (spice_level 0-3).
  * flag  - yes/no, stored as 1/0 (travels_well, reheats_well).

Unlike diet tags these are not rules a plan must obey. Every vocabulary is closed: an
unknown word is an error rather than a new tag, because a typo ("chiken") would
otherwise count as a different protein and make two identical meals look varied.
An empty cell means "not tagged yet"; tag columns that need a way to say "nothing of
this kind" have an explicit "none". Fill the columns with proj2/scripts/menu_tags.py.
"""

from dataclasses import dataclass, field

from proj2.dietary import normalize_tag


@dataclass(frozen=True)
class TagColumn:
    """One descriptive MenuItem column and the values it accepts."""

    name: str
    kind: str = "tags"  # "tags", "level" or "flag"
    values: frozenset = frozenset()  # tags: the vocabulary
    single: bool = False  # tags: at most one value
    exclusive: str = None  # tags: a value that cannot be listed with others ("none")
    aliases: dict = field(default_factory=dict)  # tags: other spellings -> stored tag
    low: int = 0  # level: smallest allowed value
    high: int = 0  # level: largest allowed value
    help: str = ""

    @property
    def sql_type(self) -> str:
        return "TEXT" if self.kind == "tags" else "INTEGER"


_COLUMNS = [
    TagColumn(
        "cuisine",
        values=frozenset(
            {
                "american",
                "southern",
                "mexican",
                "italian",
                "greek",
                "mediterranean",
                "middle-eastern",
                "indian",
                "chinese",
                "japanese",
                "korean",
                "thai",
                "vietnamese",
                "french",
                "caribbean",
                "fusion",
            }
        ),
        aliases={"middle-east": "middle-eastern", "tex-mex": "mexican"},
        help="where the dish comes from",
    ),
    TagColumn(
        "protein",
        values=frozenset(
            {
                "chicken",
                "turkey",
                "beef",
                "pork",
                "lamb",
                "goat",
                "fish",
                "shellfish",
                "egg",
                "dairy",
                "tofu",
                "legumes",
                "nuts",
                "plant-based",
                "none",
            }
        ),
        exclusive="none",
        aliases={"eggs": "egg", "cheese": "dairy", "beans": "legumes", "seafood": "shellfish"},
        help="main protein sources",
    ),
    TagColumn(
        "flavor",
        values=frozenset(
            {
                "savory",
                "sweet",
                "spicy",
                "tangy",
                "smoky",
                "herby",
                "salty",
                "rich",
                "fresh",
                "mild",
                "bitter",
            }
        ),
        help="dominant flavors",
    ),
    TagColumn(
        "meal_type",
        values=frozenset({"breakfast", "lunch-dinner", "snack", "dessert"}),
        aliases={"lunch": "lunch-dinner", "dinner": "lunch-dinner", "main": "lunch-dinner"},
        help="when it is eaten",
    ),
    TagColumn(
        "carb_base",
        values=frozenset(
            {"rice", "pasta", "noodles", "bread", "tortilla", "potato", "grain", "none"}
        ),
        exclusive="none",
        aliases={
            "flatbread": "bread",
            "pita": "bread",
            "naan": "bread",
            "quinoa": "grain",
            "oats": "grain",
            "corn": "grain",
        },
        help="main starch",
    ),
    TagColumn(
        "cooking_method",
        values=frozenset(
            {
                "grilled",
                "fried",
                "baked",
                "roasted",
                "steamed",
                "braised",
                "simmered",
                "sauteed",
                "griddled",
                "smoked",
                "raw",
                "blended",
                "brewed",
                "frozen",
            }
        ),
        aliases={
            "deep-fried": "fried",
            "pan-fried": "fried",
            "stir-fried": "sauteed",
            "sautéed": "sauteed",
            "seared": "sauteed",
            "stewed": "simmered",
            "uncooked": "raw",
        },
        help="how it is cooked",
    ),
    TagColumn(
        "course",
        values=frozenset({"starter", "main", "side", "dessert", "drink"}),
        single=True,
        aliases={"appetizer": "starter", "entree": "main", "beverage": "drink"},
        help="its place in a meal",
    ),
    TagColumn("spice_level", kind="level", low=0, high=3, help="0 none, 1 mild, 2 medium, 3 hot"),
    TagColumn(
        "temperature",
        values=frozenset({"hot", "cold"}),
        single=True,
        aliases={"warm": "hot", "chilled": "cold", "iced": "cold"},
        help="served hot or cold",
    ),
    TagColumn(
        "texture",
        values=frozenset({"crunchy", "creamy", "soft", "chewy", "tender", "flaky", "smooth"}),
        aliases={"crispy": "crunchy", "crisp": "crunchy"},
        help="mouthfeel",
    ),
    TagColumn(
        "heaviness",
        values=frozenset({"light", "regular", "hearty"}),
        single=True,
        aliases={"heavy": "hearty", "medium": "regular"},
        help="how filling it is",
    ),
    TagColumn(
        "nutrition",
        values=frozenset(
            {"high-protein", "low-carb", "high-fiber", "low-sugar", "low-fat", "none"}
        ),
        exclusive="none",
        help="notable nutrition traits; none if nothing stands out",
    ),
    TagColumn(
        "contains",
        values=frozenset({"caffeine", "alcohol", "none"}),
        exclusive="none",
        help="caffeine or alcohol; none if neither",
    ),
    TagColumn("travels_well", kind="flag", help="still good after a delivery ride"),
    TagColumn("reheats_well", kind="flag", help="good as leftovers"),
]

COLUMNS = {column.name: column for column in _COLUMNS}
TAG_COLUMNS = tuple(COLUMNS)

## The allowed words for each list-of-tags column
TAG_VOCABULARIES = {c.name: c.values for c in _COLUMNS if c.kind == "tags"}

_YES = frozenset({"1", "yes", "y", "true", "t"})
_NO = frozenset({"0", "no", "n", "false", "f"})


def _is_empty(value) -> bool:
    return value is None or value != value or (isinstance(value, str) and not value.strip())


def normalize(column: str, value: str) -> str:
    """
    Normalizes one tag as typed into its stored form

    Args:
        column (str): A list-of-tags column, e.g. "meal_type"
        value (str): The tag as typed, e.g. "Lunch/Dinner" or "Middle Eastern"

    Returns:
        str: The tag casefolded with words joined by hyphens and aliases resolved,
            e.g. "lunch-dinner"
    """
    tag = normalize_tag(str(value).replace("/", " "))
    return COLUMNS[column].aliases.get(tag, tag)


def parse_tags(column: str, value) -> set:
    """
    Reads a stored or typed list-of-tags cell into a set of normalized tags

    Args:
        column (str): A list-of-tags column
        value (str | None): The comma-separated cell (None/NaN allowed)

    Returns:
        set: The normalized tags, known or not
    """
    if _is_empty(value):
        return set()
    return {normalize(column, tag) for tag in str(value).split(",") if tag.strip()}


def _canonical_tags(spec: TagColumn, raw):
    tags = parse_tags(spec.name, raw)
    problems = []
    unknown = sorted(tags - spec.values)
    if unknown:
        problems.append(
            f"unknown {spec.name} tag(s) {', '.join(unknown)}; "
            f"use {', '.join(sorted(spec.values))}"
        )
    if spec.exclusive in tags and len(tags) > 1:
        problems.append(
            f"{spec.name} {spec.exclusive!r} cannot be listed with other {spec.name} tags"
        )
    elif spec.single and len(tags) > 1:
        problems.append(f"{spec.name} takes one value, not {', '.join(sorted(tags))}")
    return ", ".join(sorted(tags & spec.values)), problems


def _canonical_level(spec: TagColumn, raw):
    text = str(raw).strip()
    try:
        if isinstance(raw, bool):
            raise ValueError
        level = int(text)
        if not spec.low <= level <= spec.high:
            raise ValueError
    except ValueError:
        return "", [
            f"{spec.name} must be a whole number from {spec.low} to {spec.high}, not {text!r}"
        ]
    return level, []


def _canonical_flag(spec: TagColumn, raw):
    text = str(raw).strip().casefold()
    if text in _YES:
        return 1, []
    if text in _NO:
        return 0, []
    return "", [f"{spec.name} must be yes or no, not {str(raw).strip()!r}"]


def canonical(column: str, raw):
    """
    Normalizes a cell and checks it against its column's rules

    Args:
        column (str): One of TAG_COLUMNS
        raw (str | int | None): The cell as typed or stored, e.g. "Spicy,  smoky", "2", "yes"

    Returns:
        Tuple[str | int, List[str]]: The stored value and a list of problems (empty if valid).
            The stored value is "" for an empty cell; a sorted, de-duplicated string such
            as "smoky, spicy" for tags; and an int for levels and flags (1/0).
    """
    spec = COLUMNS[column]
    if _is_empty(raw):
        return "", []
    if spec.kind == "level":
        return _canonical_level(spec, raw)
    if spec.kind == "flag":
        return _canonical_flag(spec, raw)
    return _canonical_tags(spec, raw)


def tag_clashes(item: dict) -> list:
    """
    Lists descriptive tags on one item that contradict each other

    Args:
        item (dict): Canonical values keyed by column name (missing columns are skipped)

    Returns:
        List[str]: Messages such as "low-carb but its carb base is rice"; empty if consistent
    """
    problems = []
    nutrition = parse_tags("nutrition", item.get("nutrition"))
    carbs = parse_tags("carb_base", item.get("carb_base")) - {"none"}
    if "low-carb" in nutrition and carbs:
        problems.append(f"low-carb but its carb base is {', '.join(sorted(carbs))}")
    return problems


def has_column(conn, column: str) -> bool:
    """Whether the MenuItem table has this column (older databases may not)."""
    columns = conn.execute('PRAGMA table_info("MenuItem")').fetchall()
    return any(row[1] == column for row in columns)


def ensure_columns(conn, columns) -> list:
    """
    Adds any of the given tag columns that MenuItem lacks; safe to run more than once

    A database made by init-db is brought up to date through the migrations, so a
    later `flask migrate` does not add a column twice. An older unversioned database
    gets the missing columns directly.

    Args:
        conn (sqlite3.Connection): An open database connection
        columns (Iterable[str]): Columns (TAG_COLUMNS or diet_tags) that must exist

    Returns:
        list: The columns that were missing
    """
    missing = [column for column in columns if not has_column(conn, column)]
    if not missing:
        return []
    if conn.execute("PRAGMA user_version").fetchone()[0] > 0:
        from proj2.db_cli import apply_migrations  # local import: db_cli is heavier

        apply_migrations(conn)
        return missing
    for column in missing:
        sql_type = COLUMNS[column].sql_type if column in COLUMNS else "TEXT"
        conn.execute(f'ALTER TABLE "MenuItem" ADD COLUMN {column} {sql_type}')
    conn.commit()
    return missing
