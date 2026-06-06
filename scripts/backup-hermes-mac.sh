#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: backup-hermes-mac.sh [--outdir DIR] [--repo DIR] [--dry-run]

Creates a timestamped archive of the Mac-specific Hermes config files and
writes a manifest with repo/status details and restore instructions.

Defaults:
  --outdir  ~/Backups/hermes
  --repo    /Users/james/Documents/GitHub/hermes-agent
EOF
}

OUTDIR="$HOME/Backups/hermes"
REPO="/Users/james/Documents/GitHub/hermes-agent"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --outdir)
      OUTDIR="${2:-}"
      shift 2
      ;;
    --repo)
      REPO="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "$REPO/.git" ]]; then
  echo "Error: repo not found or not a git checkout: $REPO" >&2
  exit 1
fi

mkdir -p "$OUTDIR"

TIMESTAMP="$(date +%Y-%m-%d-%H%M%S)"
BACKUP_DIR="$OUTDIR/$TIMESTAMP"
ARCHIVE="$BACKUP_DIR/hermes-mac-configs.tar.gz"
MANIFEST="$BACKUP_DIR/manifest.json"
mkdir -p "$BACKUP_DIR"

HERMES_HOME="$HOME/.hermes"
FILES=(
  "$HERMES_HOME/config.yaml"
  "$HOME/Library/LaunchAgents/ai.hermes.dashboard.plist"
  "$HOME/Library/LaunchAgents/ai.hermes.gateway.plist"
  "$HOME/.local/bin/hermes"
  "$HOME/.local/bin/git-credential-ghdesktop"
)

EXISTING=()
MISSING=()
for f in "${FILES[@]}"; do
  if [[ -e "$f" || -L "$f" ]]; then
    EXISTING+=("$f")
  else
    MISSING+=("$f")
  fi
done

repo_branch="$(git -C "$REPO" branch --show-current 2>/dev/null || true)"
repo_head="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || true)"
repo_status="$(git -C "$REPO" status --short --branch 2>/dev/null || true)"
origin_url="$(git -C "$REPO" remote get-url origin 2>/dev/null || true)"
upstream_url="$(git -C "$REPO" remote get-url upstream 2>/dev/null || true)"

export HERMES_BACKUP_HOME="$HOME"
export HERMES_BACKUP_ARCHIVE="$ARCHIVE"
export HERMES_BACKUP_MANIFEST="$MANIFEST"
export HERMES_BACKUP_TIMESTAMP="$TIMESTAMP"
export HERMES_BACKUP_REPO="$REPO"
export HERMES_BACKUP_BRANCH="$repo_branch"
export HERMES_BACKUP_HEAD="$repo_head"
export HERMES_BACKUP_STATUS="$repo_status"
export HERMES_BACKUP_ORIGIN="$origin_url"
export HERMES_BACKUP_UPSTREAM="$upstream_url"
if [[ ${#EXISTING[@]} -gt 0 ]]; then
  export HERMES_BACKUP_FILES="$(printf '%s\n' "${EXISTING[@]}")"
else
  export HERMES_BACKUP_FILES=""
fi
if [[ ${#MISSING[@]} -gt 0 ]]; then
  export HERMES_BACKUP_MISSING="$(printf '%s\n' "${MISSING[@]}")"
else
  export HERMES_BACKUP_MISSING=""
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run"
  echo "Backup dir: $BACKUP_DIR"
  echo "Would archive:"
  for f in "${EXISTING[@]}"; do
    echo "  $f"
  done
  if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "Missing files:"
    for f in "${MISSING[@]}"; do
      echo "  $f"
    done
  fi
  exit 0
fi

python3 - <<'PY'
from __future__ import annotations

import json
import os
import tarfile
from pathlib import Path

home = Path(os.environ["HERMES_BACKUP_HOME"])
archive = Path(os.environ["HERMES_BACKUP_ARCHIVE"])
manifest = Path(os.environ["HERMES_BACKUP_MANIFEST"])
repo = os.environ["HERMES_BACKUP_REPO"]
branch = os.environ["HERMES_BACKUP_BRANCH"]
head = os.environ["HERMES_BACKUP_HEAD"]
status = os.environ["HERMES_BACKUP_STATUS"]
origin = os.environ["HERMES_BACKUP_ORIGIN"]
upstream = os.environ["HERMES_BACKUP_UPSTREAM"]

files = [p for p in os.environ.get("HERMES_BACKUP_FILES", "").splitlines() if p]
missing = [p for p in os.environ.get("HERMES_BACKUP_MISSING", "").splitlines() if p]

archive.parent.mkdir(parents=True, exist_ok=True)

with tarfile.open(archive, "w:gz", compresslevel=6) as tf:
    for raw in files:
        p = Path(raw)
        if not p.exists() and not p.is_symlink():
            continue
        arcname = p.relative_to(home)
        tf.add(p, arcname=str(arcname), recursive=False)

manifest_data = {
    "created_at": os.environ.get("HERMES_BACKUP_TIMESTAMP"),
    "repo": {
        "path": repo,
        "branch": branch,
        "head": head,
        "status": status,
        "origin": origin,
        "upstream": upstream,
    },
    "files": {
        "included": files,
        "missing": missing,
    },
    "restore": [
        "Restore config.yaml to ~/.hermes/config.yaml",
        "Restore the LaunchAgents plists to ~/Library/LaunchAgents/",
        "Restore helper scripts to ~/.local/bin/",
        "Reload launchd jobs: launchctl unload/load or kickstart the two ai.hermes jobs",
        "If needed, use git to restore the repo from origin and merge upstream/main again",
    ],
    "notes": [
        "Repo is expected to live in git; this archive is only for machine-specific config and launch items.",
        "If any file was missing at backup time, it is recorded in 'files.missing'.",
    ],
}
manifest.write_text(json.dumps(manifest_data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY

archive_size="$(stat -f %z "$ARCHIVE")"
manifest_size="$(stat -f %z "$MANIFEST")"

echo "Backup complete"
echo "  Archive:  $ARCHIVE"
echo "  Size:     $archive_size bytes"
echo "  Manifest: $MANIFEST"
echo "  Manifest size: $manifest_size bytes"

echo "  Repo:     $REPO"
echo "  Branch:   ${repo_branch:-unknown}"
echo "  Head:     ${repo_head:-unknown}"

echo "  Included files: ${#EXISTING[@]}"
if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "  Missing files:"
  for f in "${MISSING[@]}"; do
    echo "    $f"
  done
fi
