#!/usr/bin/env bash
set -euo pipefail

# Hardened one-command release installer and upgrader for existing and new Remorswarm UX QA users.
# Downloads the verified GitHub Release manifest + ZIPs once, checks SHA-256, and preserves node_modules / .ux-* state.

REPO="${REMORSEARCH_REPO:-remorser58/Remorswarm_UX_QA_Skill}"
TARGET_MODE="auto"
VERSION_TAG="latest"
WITH_DESIGN_SYSTEM=0
FORCE_ARG=""
ALLOW_DOWNGRADE_ARG=""

require_value() {
  local flag="$1"
  local val="${2:-}"
  if [[ -z "$val" || "$val" == -* ]]; then
    echo "Error: $flag requires a value" >&2
    exit 2
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      require_value "--target" "${2:-}"
      TARGET_MODE="$2"
      shift 2
      ;;
    --version)
      require_value "--version" "${2:-}"
      VERSION_TAG="$2"
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

if ! [[ "$REPO" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
  echo "Error: Invalid REMORSEARCH_REPO value: $REPO" >&2
  exit 2
fi

if [[ "$VERSION_TAG" != "latest" ]] && ! [[ "$VERSION_TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
  echo "Error: --version must be 'latest' or 'vX.Y.Z'" >&2
  exit 2
fi

if [[ "$VERSION_TAG" != "latest" ]]; then
  ALLOW_DOWNGRADE_ARG="--allow-downgrade"
fi

is_python310_plus() {
  local bin="$1"
  [[ -n "$bin" && "$bin" == /* && -x "$bin" ]] || return 1
  "$bin" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null
}

PYTHON_BIN=""
CANDIDATES=(
  "/opt/homebrew/bin/python3"
  "/usr/local/bin/python3"
)
for minor in 15 14 13 12 11 10; do
  CANDIDATES+=(
    "/opt/homebrew/opt/python@3.${minor}/bin/python3.${minor}"
    "/Library/Frameworks/Python.framework/Versions/3.${minor}/bin/python3.${minor}"
    "$(command -v "python3.${minor}" 2>/dev/null || true)"
  )
done
CANDIDATES+=("$(command -v python3 2>/dev/null || true)")

for candidate in "${CANDIDATES[@]}"; do
  if is_python310_plus "$candidate"; then
    PYTHON_BIN="$candidate"
    break
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

CURL_OPTS=(--proto '=https' --proto-redir '=https' --tlsv1.2 --connect-timeout 15 --max-time 120 --max-filesize 67108864)

if ! curl -fsSL "${CURL_OPTS[@]}" "$MANIFEST_URL" -o "$TMP_DIR/release-manifest.json"; then
  echo "Failed to fetch release manifest from $MANIFEST_URL" >&2
  exit 2
fi

# Strictly validate manifest schema, tag, filename, sha256, and byte count in Python before downloading assets.
PARSED_META="$("$PYTHON_BIN" - "$TMP_DIR/release-manifest.json" <<'PY'
import json, re, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    m = json.load(fh)
if not isinstance(m, dict) or m.get("schema_version") != "remorswarm-release-manifest.v1":
    raise SystemExit("Unsupported release manifest schema")
tag = m.get("tag") or f"v{m.get('version', '')}"
if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", str(tag)):
    raise SystemExit(f"Invalid release tag in manifest: {tag!r}")
asset = (m.get("assets") or {}).get("remorsearch-ux-qa")
if not isinstance(asset, dict):
    raise SystemExit("Manifest missing remorsearch-ux-qa asset")
fname = asset.get("filename")
sha = asset.get("sha256")
size = asset.get("bytes")
if not isinstance(fname, str) or not re.fullmatch(r"[A-Za-z0-9._-]+\.zip", fname):
    raise SystemExit(f"Invalid asset filename in manifest: {fname!r}")
if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
    raise SystemExit("Invalid asset sha256 in manifest")
if type(size) is not int or size <= 0 or size > 67108864:
    raise SystemExit("Invalid asset byte count in manifest")
print(f"{tag}|{fname}|{sha}|{size}")
PY
)"

IFS='|' read -r RESOLVED_TAG ASSET_FILE ASSET_SHA ASSET_BYTES <<< "$PARSED_META"

# Always fetch assets from the tag-pinned URL (prevents /releases/latest/download/ TOCTOU race).
ASSET_URL="https://github.com/$REPO/releases/download/$RESOLVED_TAG/$ASSET_FILE"
PINNED_MANIFEST_URL="https://github.com/$REPO/releases/download/$RESOLVED_TAG/release-manifest.json"

# Save to fixed filename regardless of manifest string.
curl -fsSL "${CURL_OPTS[@]}" "$ASSET_URL" -o "$TMP_DIR/primary.zip"

"$PYTHON_BIN" - "$TMP_DIR/primary.zip" "$ASSET_SHA" "$ASSET_BYTES" "$TMP_DIR/update_skill.py" <<'PY'
import hashlib, pathlib, stat, sys, zipfile

zip_path = pathlib.Path(sys.argv[1])
expected_sha = sys.argv[2]
expected_bytes = int(sys.argv[3])
out_path = pathlib.Path(sys.argv[4])

raw = zip_path.read_bytes()
if len(raw) != expected_bytes or hashlib.sha256(raw).hexdigest() != expected_sha:
    raise SystemExit("SHA-256 verification failed for downloaded release archive")

member = "remorsearch-ux-qa/scripts/update_skill.py"
with zipfile.ZipFile(zip_path) as zf:
    names = zf.namelist()
    if names.count(member) != 1:
        raise SystemExit(f"Archive member validation failed for {member}")
    info = zf.getinfo(member)
    if stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK:
        raise SystemExit("Refusing symlink updater script in archive")
    if info.file_size <= 0 or info.file_size > 1024 * 1024:
        raise SystemExit("Unexpected update_skill.py size in archive")
    out_path.write_bytes(zf.read(member))
out_path.chmod(0o700)
PY

APPLY_ARGS=(
  --target "$SKILL_DIR"
  --repo "$REPO"
  --manifest-url "$PINNED_MANIFEST_URL"
  --local-manifest "$TMP_DIR/release-manifest.json"
  --local-primary-zip "$TMP_DIR/primary.zip"
)
if [[ $WITH_DESIGN_SYSTEM -eq 1 ]]; then
  APPLY_ARGS+=(--with-design-system)
fi
if [[ -n "$FORCE_ARG" ]]; then
  APPLY_ARGS+=("$FORCE_ARG")
fi
if [[ -n "$ALLOW_DOWNGRADE_ARG" ]]; then
  APPLY_ARGS+=("$ALLOW_DOWNGRADE_ARG")
fi

# Never use exec so EXIT trap always removes TMP_DIR.
"$PYTHON_BIN" "$TMP_DIR/update_skill.py" apply "${APPLY_ARGS[@]}"
