#!/usr/bin/env bash
# zerver_scp.sh — sync changed files to the zerver test server
#
# Workflow:
#   1. Bring zerver's working tree up to origin/main
#      (git fetch + force-checkout so previously-merged PR files are current)
#   2. Overlay the files that differ between the current branch and main
#      so the new/in-progress work is applied on top
#
# Usage:
#   ./zerver_scp.sh            # update to main, then overlay branch diff
#   ./zerver_scp.sh --dry-run  # show what would be sent without doing it

set -euo pipefail

REMOTE_USER="milan"
REMOTE_HOST_LAN="192.168.111.5"
REMOTE_HOST_EXT="85.163.61.171"
REMOTE_PORT_EXT="8361"
REMOTE_DIR="/home/milan/MedCover"
DRY_RUN=false

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
fi

# ── Resolve host ───────────────────────────────────────────────────────────────
if nc -z -w 2 "$REMOTE_HOST_LAN" 22 &>/dev/null; then
    REMOTE_HOST="$REMOTE_HOST_LAN"
    SSH_OPTS=()
    echo "Using LAN address: $REMOTE_HOST"
else
    REMOTE_HOST="$REMOTE_HOST_EXT"
    SSH_OPTS=(-p "$REMOTE_PORT_EXT")
    echo "LAN unreachable — using external address: $REMOTE_HOST (port $REMOTE_PORT_EXT)"
fi

# ── Step 1: pull origin/main on zerver ────────────────────────────────────────
# git checkout -f origin/main -- . updates tracked AND untracked files that
# exist in the remote tree, without touching gitignored files (.env, etc.)
echo "Pulling origin/main on zerver..."
if ! $DRY_RUN; then
    ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$REMOTE_HOST" \
        "cd '$REMOTE_DIR' && git fetch origin && git checkout -f origin/main -- . && echo '  ✓ zerver working tree at origin/main'"
fi

# ── Step 2: overlay branch-specific files ─────────────────────────────────────
FILES=$(
  {
    git diff main...HEAD --name-only --diff-filter=d 2>/dev/null || true
    git diff --name-only --diff-filter=d 2>/dev/null || true
    git diff --cached --name-only --diff-filter=d 2>/dev/null || true
  } | sort -u
)

if [[ -z "$FILES" ]]; then
    echo "No branch-specific files to overlay — zerver is at origin/main."
    exit 0
fi

COUNT=$(echo "$FILES" | wc -l | tr -d ' ')
echo "Overlaying $COUNT branch-specific file(s):"
echo "$FILES" | sed 's/^/  /'
echo ""

if $DRY_RUN; then
    echo "[dry-run] Would sync to $REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
    exit 0
fi

# shellcheck disable=SC2086
tar czf - $FILES | ssh "${SSH_OPTS[@]}" "$REMOTE_USER@$REMOTE_HOST" \
    "cd '$REMOTE_DIR' && tar xzf -"

echo "✓ Sync complete: zerver is at origin/main + $COUNT branch-specific file(s)"
