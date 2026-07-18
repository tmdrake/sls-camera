#!/usr/bin/env bash
# Remove files created by install-field-app.sh (user-local packaging).
#
# Does NOT by default:
#   - delete the git checkout or viewer/.venv
#   - purge apt packages (freenect, etc.)
#   - reverse gspca blacklist / udev from fix-kinect-access.sh
#
# Optional:
#   --purge-apt-deps  remove only *safe* SLS seeds (freenect, portaudio, …)
#                     never purges python3 / ca-certificates / libgl1 / etc.
#                     see packages/apt-purge-safe.txt
#
# Usage:
#   ./software/linux/scripts/uninstall-field-app.sh
#   ./software/linux/scripts/uninstall-field-app.sh --keep-launcher   # only drop autostart
#   ./software/linux/scripts/uninstall-field-app.sh --purge-apt-deps
#   ./software/linux/scripts/uninstall-field-app.sh --dry-run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LINUX_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PURGE_SAFE="${LINUX_ROOT}/packages/apt-purge-safe.txt"

KEEP_LAUNCHER=0
PURGE_APT=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-launcher) KEEP_LAUNCHER=1; shift ;;
    --purge-apt-deps) PURGE_APT=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

rm_f() {
  local f="$1"
  if [[ ! -e "$f" ]]; then
    return
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "DRY-RUN: rm ${f}"
  else
    rm -f "$f"
    echo "removed ${f}"
  fi
}

WRAPPER="${HOME}/.local/bin/sls-camera"
DESKTOP_APP="${HOME}/.local/share/applications/sls-camera.desktop"
DESKTOP_AUTO="${HOME}/.config/autostart/sls-camera.desktop"
MARKER_DIR="${HOME}/.local/share/sls-camera"
MARKER="${MARKER_DIR}/install-manifest.txt"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/sls-camera"
APT_RECORD="${STATE_DIR}/apt-seeds-installed.txt"

# Prefer paths recorded by install
if [[ -f "$MARKER" ]]; then
  while IFS= read -r line; do
    [[ "$line" =~ ^# ]] && continue
    [[ -z "$line" ]] && continue
    case "$line" in
      WRAPPER=*) WRAPPER="${line#WRAPPER=}" ;;
      DESKTOP_APP=*) DESKTOP_APP="${line#DESKTOP_APP=}" ;;
      DESKTOP_AUTO=*) DESKTOP_AUTO="${line#DESKTOP_AUTO=}" ;;
    esac
  done <"$MARKER"
fi

echo "=== SLS field app uninstall ==="

rm_f "$DESKTOP_AUTO"

if [[ "$KEEP_LAUNCHER" -eq 0 ]]; then
  rm_f "$DESKTOP_APP"
  rm_f "$WRAPPER"
  rm_f "$MARKER"
  # remove marker dir if empty
  if [[ "$DRY_RUN" -eq 0 && -d "$MARKER_DIR" ]]; then
    rmdir "$MARKER_DIR" 2>/dev/null || true
  fi
else
  echo "kept launcher (--keep-launcher): ${WRAPPER} ${DESKTOP_APP}"
  if [[ "$DRY_RUN" -eq 0 && -f "$MARKER" ]]; then
    {
      echo "# Updated by uninstall --keep-launcher on $(date -Iseconds 2>/dev/null || date)"
      echo "WRAPPER=${WRAPPER}"
      echo "DESKTOP_APP=${DESKTOP_APP}"
      echo "DESKTOP_AUTO="
      echo "WITH_AUTOSTART=0"
    } >"$MARKER"
  fi
fi

if [[ "$PURGE_APT" -eq 1 ]]; then
  echo
  echo "--- purge safe apt seeds (optional) ---"
  if [[ ! -f "$PURGE_SAFE" ]]; then
    echo "WARN: ${PURGE_SAFE} missing — skip purge"
  elif ! command -v apt-get >/dev/null 2>&1; then
    echo "WARN: apt-get not found — skip purge"
  else
    mapfile -t SAFE < <(grep -vE '^\s*(#|$)' "$PURGE_SAFE" || true)
    # Only purge packages that are actually installed
    TO_PURGE=()
    for p in "${SAFE[@]}"; do
      p="${p// /}"
      [[ -z "$p" ]] && continue
      if dpkg -s "$p" >/dev/null 2>&1; then
        TO_PURGE+=("$p")
      fi
    done
    if [[ ${#TO_PURGE[@]} -eq 0 ]]; then
      echo "  (none of the safe-seed packages are installed)"
    else
      echo "  will purge: ${TO_PURGE[*]}"
      echo "  (never purges python3 / ca-certificates / GUI base libs)"
      if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "DRY-RUN: sudo apt-get purge -y ${TO_PURGE[*]}"
      else
        sudo DEBIAN_FRONTEND=noninteractive apt-get purge -y "${TO_PURGE[@]}" || true
        sudo DEBIAN_FRONTEND=noninteractive apt-get autoremove -y || true
      fi
    fi
  fi
  rm_f "$APT_RECORD"
fi

echo
echo "Done. Git checkout and viewer/.venv were left untouched."
if [[ "$PURGE_APT" -eq 0 ]]; then
  echo "Apt packages were left installed (default)."
  echo "  Optional: $0 --purge-apt-deps   # freenect/portaudio/espeak only"
fi
echo "To also reverse Kinect gspca blacklist (manual):"
echo "  sudo rm -f /etc/modprobe.d/blacklist-gspca-kinect.conf"
echo "  # then reboot or modprobe gspca_kinect if you want webcam mode again"
