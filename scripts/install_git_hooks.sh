#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.githooks"

if [[ ! -d "$HOOKS_DIR" ]]; then
  echo "❌ Missing $HOOKS_DIR"
  exit 1
fi

chmod +x "$HOOKS_DIR/pre-commit" || true

git -C "$REPO_ROOT" config core.hooksPath .githooks

echo "✅ Git hooks installed"
echo "- core.hooksPath set to .githooks"
echo "- pre-commit: $HOOKS_DIR/pre-commit"
