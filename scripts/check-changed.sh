#!/usr/bin/env bash
#
# Run Black and Ruff over the Python files this branch changed.
#
# The repo has a large backlog of unformatted files and existing lint errors, so a
# whole-tree gate cannot be turned on without one enormous reformat commit that
# conflicts with every open branch. This checks only what you touched, which keeps new
# code to the standard without rewriting history under anyone.
#
#   scripts/check-changed.sh [base-ref]     # base-ref defaults to dev-branch
#
# Exits 0 when every changed Python file is clean, or when none changed.

set -euo pipefail

BASE="${1:-dev-branch}"

cd "$(dirname "$0")/.."

# Prefer the remote-tracking ref: in CI the local branch of that name usually does not exist.
base_ref=""
for candidate in "origin/$BASE" "$BASE"; do
    if git rev-parse --verify --quiet "$candidate" >/dev/null; then
        base_ref="$candidate"
        break
    fi
done

if [ -z "$base_ref" ]; then
    echo "Base ref '$BASE' not found; comparing against the previous commit instead."
    base_ref="HEAD~1"
fi

# Diff from the merge base, so commits that landed on the base after we branched are not
# attributed to us.
diff_from="$(git merge-base "$base_ref" HEAD)"

# Standing on the base branch itself, HEAD is its own merge base. Locally that is a
# pre-commit run and the uncommitted work is the point; in CI the tree is clean, so the
# commit just pushed is what needs checking.
if [ "$diff_from" = "$(git rev-parse HEAD)" ] && [ -z "$(git status --porcelain)" ]; then
    diff_from="HEAD~1"
fi

# Diffed against the working tree rather than HEAD, so staged and unstaged edits count.
# pre-commit-check.sh runs before the commit exists, and a gate that only sees committed
# files would pass it and then fail in CI. In CI the tree is clean, so the two agree.
# -z and xargs -0 so paths with spaces survive; --diff-filter=d drops deleted files, which
# Black cannot open.
changed="$(mktemp)"
trap 'rm -f "$changed"' EXIT
{
    git diff -z --name-only --diff-filter=d "$diff_from" -- '*.py'
    # New files are invisible to git diff until staged; catch them too.
    git ls-files -z --others --exclude-standard -- '*.py'
} | sort -zu >"$changed"

if [ ! -s "$changed" ]; then
    echo "No Python files changed against $base_ref; nothing to check."
    exit 0
fi

echo "Changed Python files, against $base_ref:"
tr '\0' '\n' <"$changed" | sed 's/^/  /'
echo

# --force-exclude keeps pyproject.toml's exclusions (proj2/site) honoured even though the
# paths are passed explicitly, which otherwise overrides them.
status=0

echo "Black:"
xargs -0 "${PYTHON:-python}" -m black --check --force-exclude -- <"$changed" || status=1
echo

echo "Ruff:"
xargs -0 "${PYTHON:-python}" -m ruff check --force-exclude -- <"$changed" || status=1

if [ "$status" -ne 0 ]; then
    echo
    echo "Fix with:  python -m black <file>   and   python -m ruff check --fix <file>"
fi

exit "$status"
