#!/usr/bin/env bash
set -euo pipefail

# One-command release installer and upgrader for existing and new Remorswarm UX QA users.
# Downloads the verified GitHub Release ZIP + release-manifest.json and preserves node_modules / run state.

REPO="${REMORSEARCH_REPO:-remorser58/Remorswarm_UX_QA_Skill}"
TARGET_MODE="auto"
VERSION_TAG="latest"
WITH_DESIGN_SYSTEM=0
FORCE_ARG=""
CUSTOM_TARGET=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET_MODE="${2:?--target requires a value (claude|codex|gemini|/path/to/dir)}"
      shift 2
      ;;
    --version)
      VERSION_TAG="${2:?--version requires vX.Y.Z or latest}"
      shift 2
      ;;
    --with-design-system)
      WITH_DESIGN_SYSTEM=1
      shift
      ;;
    --force)
      FORCE_ARG="--force"
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: install.sh [OPTIONS]
  --target claude|codex|gemini|PATH   Skills parent or remorsearch-ux-qa folder (default: auto-detect)
  --version latest|vX.Y.Z             Release tag to install/update to (default: latest)
  --with-design-system                Also install/update sibling react-design-system skill
  --force                             Overwrite local edits or reinstall same version
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

PYTHON_BIN=""
for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 "$(command -v python3 || true)"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PYTHON_BIN="$candidate"
      break
    fi
  fi
done

if [[ -z "$PYTHON_BIN" ]]; then
  echo "Error: Python 3.10+ is required to verify and extract releases cleanly." >&2
  exit 2
fi

resolve_skill_dir() {
  case "$TARGET_MODE" in
    claude) echo "$HOME/.claude/skills/remorsearch-ux-qa" ;;
    codex) echo "$HOME/.codex/skills/remorsearch-ux-qa" ;;
    gemini) echo "$HOME/.gemini/config/skills/remorsearch-ux-qa" ;;
    auto)
      for dir in \
        "$HOME/.claude/skills/remorsearch-ux-qa" \
        "$HOME/.codex/skills/remorsearch-ux-qa" \
        "$HOME/.gemini/config/skills/remorsearch-ux-qa"; do
        if [[ -d "$dir" ]]; then
          echo "$dir"
          return 0
        fi
      done
      echo "$HOME/.claude/skills/remorsearch-ux-qa"
      ;;
    *)
      if [[ "$(basename "$TARGET_MODE")" == "remorsearch-ux-qa" ]]; then
        echo "$TARGET_MODE"
      else
        echo "${TARGET_MODE%/}/remorsearch-ux-qa"
      fi
      ;;
  esac
}

SKILL_DIR="$(resolve_skill_dir)"
if [[ "$VERSION_TAG" == "latest" ]]; then
  MANIFEST_URL="https://github.com/$REPO/releases/latest/download/release-manifest.json"
else
  MANIFEST_URL="https://github.com/$REPO/releases/download/$VERSION_TAG/release-manifest.json"
fi

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if ! curl -fsSL "$MANIFEST_URL" -o "$TMP_DIR/release-manifest.json"; then
  echo "Failed to fetch release manifest from $MANIFEST_URL" >&2
  exit 2
fi

read -r ASSET_FILE ASSET_SHA ASSET_BYTES RELEASE_VER < <("$PYTHON_BIN" -c '
import json, sys
m = json.load(open(sys.argv[1], encoding="utf-8"))
a = m["assets"]["remorsearch-ux-qa"]
print(a["filename"], a["sha256"], a["bytes"], m["version"])
' "$TMP_DIR/release-manifest.json")

if [[ "$VERSION_TAG" == "latest" ]]; then
  ASSET_URL="https://github.com/$REPO/releases/latest/download/$ASSET_FILE"
else
  ASSET_URL="https://github.com/$REPO/releases/download/$VERSION_TAG/$ASSET_FILE"
fi

curl -fsSL "$ASSET_URL" -o "$TMP_DIR/$ASSET_FILE"

"$PYTHON_BIN" -c '
import hashlib, pathlib, sys
p = pathlib.Path(sys.argv[1])
data = p.read_bytes()
if len(data) != int(sys.argv[3]) or hashlib.sha256(data).hexdigest() != sys.argv[2]:
    raise SystemExit("SHA-256 verification failed for release archive")
' "$TMP_DIR/$ASSET_FILE" "$ASSET_SHA" "$ASSET_BYTES"

mkdir -p "$(dirname "$SKILL_DIR")"
"$PYTHON_BIN" -c '
import pathlib, sys, zipfile
archive_path = sys.argv[1]
out_path = pathlib.Path(sys.argv[2])
member = "remorsearch-ux-qa/scripts/update_skill.py"
with zipfile.ZipFile(archive_path) as zf:
    info = zf.getinfo(member)
    if (info.external_attr >> 16) & 0o170000 == 0o120000:
        raise SystemExit("Refusing symlink updater script in archive")
    out_path.write_bytes(zf.read(member))
out_path.chmod(0o700)
' "$TMP_DIR/$ASSET_FILE" "$TMP_DIR/update_skill.py"

APPLY_ARGS=(--target "$SKILL_DIR" --repo "$REPO" --manifest-url "$MANIFEST_URL")
if [[ $WITH_DESIGN_SYSTEM -eq 1 ]]; then
  APPLY_ARGS+=(--with-design-system)
fi
if [[ -n "$FORCE_ARG" ]]; then
  APPLY_ARGS+=("$FORCE_ARG")
fi

exec "$PYTHON_BIN" "$TMP_DIR/update_skill.py" apply "${APPLY_ARGS[@]}"
