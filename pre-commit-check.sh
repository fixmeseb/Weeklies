#!/bin/bash
set -e

echo "🔍 Running pre-commit checks..."
echo ""

cd proj2

echo "1️⃣ Checking code formatting with Black..."
black --check . || {
    echo "❌ Black formatting check failed!"
    echo "Run: black proj2/ to auto-fix"
    exit 1
}
echo "✅ Black check passed"
echo ""

echo "2️⃣ Linting with Ruff..."
ruff check . || {
    echo "❌ Ruff linting failed!"
    echo "Run: ruff check proj2/ --fix to auto-fix"
    exit 1
}
echo "✅ Ruff check passed"
echo ""

cd ..

echo "3️⃣ Running tests..."
pytest -q --maxfail=1 || {
    echo "❌ Tests failed!"
    exit 1
}
echo "✅ All tests passed"
echo ""

echo "🎉 All checks passed! Ready to commit."