#!/usr/bin/env bash
# Install host apt seeds for the SLS field app (issue #2 / #3).
#
# Safe install rules (from appliance Phase 1 lessons):
#   1. Install SEEDS only — never blanket `dpkg -i vendor/debs/*.deb`
#   2. Prefer apt archive cache + `apt-get install --no-download` when debs exist
#   3. Let apt resolve OR-alternatives (libjack*, libavcodec vs *-extra)
#   4. SLS_OFFLINE=1 refuses network fallback if the cache is incomplete
#
# Usage:
#   ./software/linux/scripts/install-apt-deps.sh
#   ./software/linux/scripts/install-apt-deps.sh --deb-cache /path/to/debs
#   SLS_OFFLINE=1 ./software/linux/scripts/install-apt-deps.sh --deb-cache ./vendor/debs
#   ./software/linux/scripts/install-apt-deps.sh --print-seeds
#   ./software/linux/scripts/install-apt-deps.sh --dry-run
#
# Env:
#   SLS_DEB_CACHE   directory of .deb files (same as --deb-cache)
#   SLS_OFFLINE=1   fail if cache cannot satisfy seeds (no apt update / download)
#   SLS_APT_YES=1   pass -y to apt (default when non-interactive / scripted)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LINUX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${LINUX_ROOT}/../.." && pwd)"
SEED_FILE="${LINUX_ROOT}/packages/apt-packages.txt"

DEB_CACHE="${SLS_DEB_CACHE:-}"
DRY_RUN=0
PRINT_SEEDS=0
ASSUME_YES="${SLS_APT_YES:-1}"

usage() {
  sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --deb-cache)
      DEB_CACHE="${2:-}"
      shift 2
      ;;
    --deb-cache=*)
      DEB_CACHE="${1#*=}"
      shift
      ;;
    --dry-run) DRY_RUN=1; shift ;;
    --print-seeds) PRINT_SEEDS=1; shift ;;
    -h|--help) usage ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      ;;
  esac
done

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: $*"
  else
    "$@"
  fi
}

# Auto-detect sibling firmware offline mirror when not specified
if [[ -z "$DEB_CACHE" ]]; then
  for cand in \
    "${REPO_ROOT}/../sls-camera-firmware/vendor/debs" \
    "${HOME}/sls-camera-firmware/vendor/debs" \
    "${LINUX_ROOT}/vendor/debs" \
    "${REPO_ROOT}/vendor/debs"
  do
    if compgen -G "${cand}/*.deb" >/dev/null 2>&1; then
      DEB_CACHE="$cand"
      break
    fi
  done
fi

resolve_pkg() {
  local p="$1"
  if apt-cache show "$p" >/dev/null 2>&1; then
    echo "$p"
    return 0
  fi
  case "$p" in
    libfreenect0.5)
      if apt-cache show libfreenect0.5t64 >/dev/null 2>&1; then
        echo "libfreenect0.5t64"
        return 0
      fi
      ;;
    libfreenect0.5t64)
      if apt-cache show libfreenect0.5 >/dev/null 2>&1; then
        echo "libfreenect0.5"
        return 0
      fi
      ;;
  esac
  return 1
}

load_seeds() {
  local -a raw=()
  local p rp
  if [[ ! -f "$SEED_FILE" ]]; then
    echo "ERROR: seed list missing: ${SEED_FILE}" >&2
    exit 1
  fi
  mapfile -t raw < <(grep -vE '^\s*(#|$)' "$SEED_FILE" || true)
  SEEDS=()
  for p in "${raw[@]}"; do
    p="${p// /}"
    [[ -z "$p" ]] && continue
    if rp="$(resolve_pkg "$p")"; then
      if [[ "$rp" != "$p" ]]; then
        echo "  resolve: $p → $rp"
      fi
      SEEDS+=("$rp")
    else
      # Keep unresolved seeds for online install attempts (apt may still find them)
      echo "  note: no apt-cache candidate yet: $p (kept as seed)"
      SEEDS+=("$p")
    fi
  done
  # De-dupe while preserving order
  local -A seen=()
  local -a uniq=()
  for p in "${SEEDS[@]}"; do
    [[ -n "${seen[$p]:-}" ]] && continue
    seen[$p]=1
    uniq+=("$p")
  done
  SEEDS=("${uniq[@]}")
}

if [[ "$PRINT_SEEDS" -eq 1 ]]; then
  load_seeds
  printf '%s\n' "${SEEDS[@]}"
  exit 0
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "ERROR: apt-get not found (this installer targets Debian/Ubuntu)." >&2
  exit 1
fi

echo "=== SLS apt deps (seeds) ==="
echo "  seeds:  ${SEED_FILE}"
if [[ -n "$DEB_CACHE" ]]; then
  echo "  cache:  ${DEB_CACHE}"
else
  echo "  cache:  (none — online install)"
fi
echo "  offline strict: ${SLS_OFFLINE:-0}"
echo

load_seeds
if [[ ${#SEEDS[@]} -eq 0 ]]; then
  echo "ERROR: no seed packages resolved" >&2
  exit 1
fi
echo "Installing ${#SEEDS[@]} seed packages via apt (transitive deps resolved by apt)…"
printf '  %s\n' "${SEEDS[@]}"
echo

APT_YES=()
if [[ "$ASSUME_YES" == "1" || "$ASSUME_YES" == "yes" ]]; then
  APT_YES=(-y)
fi

install_from_cache() {
  local cache="$1"
  local n
  n=$(find "$cache" -maxdepth 1 -name '*.deb' 2>/dev/null | wc -l | tr -d ' ')
  if [[ "${n:-0}" -lt 1 ]]; then
    return 1
  fi
  echo "--- offline-friendly path: apt archive cache ($n debs) ---"
  echo "  (never dpkg -i *.deb — avoids libjack0 / libav*-extra conflicts)"
  local ARCHIVES=/var/cache/apt/archives
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: cp ${cache}/*.deb → ${ARCHIVES}/"
    echo "DRY-RUN: apt-get install ${APT_YES[*]:-} --no-install-recommends --no-download ${SEEDS[*]}"
    return 0
  fi
  sudo mkdir -p "$ARCHIVES"
  # Prefer not clobbering newer packages already in the archive
  sudo cp -n "$cache"/*.deb "$ARCHIVES/" 2>/dev/null \
    || sudo cp "$cache"/*.deb "$ARCHIVES/" 2>/dev/null \
    || true

  set +e
  if [[ "${SLS_OFFLINE:-0}" == "1" ]]; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get install \
      "${APT_YES[@]}" --no-install-recommends --no-download "${SEEDS[@]}"
    rc=$?
  else
    sudo DEBIAN_FRONTEND=noninteractive apt-get install \
      "${APT_YES[@]}" --no-install-recommends --no-download "${SEEDS[@]}"
    rc=$?
    if [[ "$rc" -ne 0 ]]; then
      echo "WARN: --no-download incomplete; retrying with network allowed…"
      sudo DEBIAN_FRONTEND=noninteractive apt-get update || true
      sudo DEBIAN_FRONTEND=noninteractive apt-get install \
        "${APT_YES[@]}" --no-install-recommends "${SEEDS[@]}"
      rc=$?
    fi
  fi
  set -e
  return "$rc"
}

install_online() {
  echo "--- online path: apt-get install seeds ---"
  if [[ "${SLS_OFFLINE:-0}" == "1" ]]; then
    echo "ERROR: no usable deb cache and SLS_OFFLINE=1." >&2
    echo "  Provide --deb-cache DIR (or sibling sls-camera-firmware/vendor/debs)." >&2
    echo "  Build cache: sls-camera-firmware/scripts/10-fetch-offline.sh (FETCH_DEPS=1)" >&2
    return 1
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: apt-get update"
    echo "DRY-RUN: apt-get install ${APT_YES[*]:-} --no-install-recommends ${SEEDS[*]}"
    return 0
  fi
  sudo DEBIAN_FRONTEND=noninteractive apt-get update
  sudo DEBIAN_FRONTEND=noninteractive apt-get install \
    "${APT_YES[@]}" --no-install-recommends "${SEEDS[@]}"
}

rc=1
if [[ -n "$DEB_CACHE" && -d "$DEB_CACHE" ]] \
  && compgen -G "${DEB_CACHE}/*.deb" >/dev/null 2>&1; then
  if install_from_cache "$DEB_CACHE"; then
    rc=0
  else
    rc=$?
    if [[ "${SLS_OFFLINE:-0}" == "1" ]]; then
      echo "ERROR: offline apt install failed (SLS_OFFLINE=1)." >&2
      echo "  Re-fetch recursive deps: firmware scripts/10-fetch-offline.sh FETCH_DEPS=1" >&2
      exit 1
    fi
    echo "WARN: cache path failed (rc=$rc); falling back to online seeds…"
    install_online || rc=$?
  fi
else
  if [[ -n "$DEB_CACHE" ]]; then
    echo "WARN: deb cache empty or missing: ${DEB_CACHE}"
  fi
  install_online || rc=$?
fi

if [[ "${rc:-1}" -ne 0 ]]; then
  echo "ERROR: apt seed install failed (rc=${rc})." >&2
  echo "  See GitHub #2 / #3 and software/linux/docs/FIELD-INSTALL.md" >&2
  exit "${rc}"
fi

# Write a small record for uninstall / audit (user-writable)
RECORD_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/sls-camera"
RECORD="${RECORD_DIR}/apt-seeds-installed.txt"
if [[ "$DRY_RUN" -eq 0 ]]; then
  mkdir -p "$RECORD_DIR"
  {
    echo "# Written by install-apt-deps.sh on $(date -Iseconds 2>/dev/null || date)"
    echo "# Seeds requested (not every transitive dep):"
    printf '%s\n' "${SEEDS[@]}"
  } >"$RECORD"
  echo "  record: ${RECORD}"
fi

echo
echo "=== apt deps OK ==="
echo "NOTE: Kinect mic firmware is separate: sudo apt install kinect-audio-setup"
echo "NOTE: do not dpkg -i every recursive deb (OR-alternative conflicts — #3)."
echo "Firmware offline mirror: https://github.com/tmdrake/sls-camera-firmware/blob/main/docs/OFFLINE-MIRROR.md"
exit 0
