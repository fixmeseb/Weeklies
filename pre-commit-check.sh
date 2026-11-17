#!/bin/bash
set -e

echo "🔍 Running pre-commit checks..."
echo ""

echo "1️⃣ Checking Black and Ruff on the files you changed..."
# Scoped to your own changes, matching the CI lint job. The whole tree does not pass
# yet, so a tree-wide check here would fail on files you never touched.
bash scripts/check-changed.sh "${1:-dev-branch}" || {
    echo "❌ Formatting or lint check failed on a file you changed!"
    exit 1
}
echo "✅ Black and Ruff passed"
echo ""

echo "2️⃣ Running tests (excluding LLM tests)..."
pytest -m "not llm" -q --maxfail=1 || {
    echo "❌ Tests failed!"
    exit 1
}
echo "✅ All tests passed"
echo ""

echo "🎉 All checks passed! Ready to commit."