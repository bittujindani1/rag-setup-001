#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
BOT_DIR="$ROOT_DIR/BOT"
CHAINLIT_HOST="${CHAINLIT_HOST:-127.0.0.1}"
CHAINLIT_PORT="${CHAINLIT_PORT:-5101}"
CHAINLIT_URL=""
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv_local/Scripts/python}"
UI_LOG="$ROOT_DIR/.venv_local_ui.log"
UI_ERR_LOG="$ROOT_DIR/.venv_local_ui.err.log"
WINDOWS_PYTHON="C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
PORT_SCAN_LIMIT="${PORT_SCAN_LIMIT:-20}"

to_windows_path() {
  local path="$1"
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$path"
    return
  fi
  printf '%s\n' "$path"
}

load_env() {
  if [[ -f "$ENV_FILE" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
  fi
}

is_port_available() {
  local port="$1"
  "$WINDOWS_PYTHON" -Command "try { \$listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('${CHAINLIT_HOST}'), ${port}); \$listener.Start(); \$listener.Stop(); exit 0 } catch { exit 1 }" >/dev/null 2>&1
}

select_chainlit_port() {
  local candidate="$CHAINLIT_PORT"
  local attempts=0

  while (( attempts < PORT_SCAN_LIMIT )); do
    if is_port_available "$candidate"; then
      CHAINLIT_PORT="$candidate"
      CHAINLIT_URL="http://${CHAINLIT_HOST}:${CHAINLIT_PORT}/login"
      return 0
    fi
    candidate=$((candidate + 1))
    attempts=$((attempts + 1))
  done

  return 1
}

print_summary() {
  local status="$1"
  echo
  echo "UI Restart Summary"
  echo "URL: $CHAINLIT_URL"
  echo "Status: $status"
  echo "Logs:"
  echo "  $UI_LOG"
  echo "  $UI_ERR_LOG"
}

load_env
export DEBUG=false
REQUESTED_CHAINLIT_PORT="$CHAINLIT_PORT"

WINDOWS_ROOT_DIR="$(to_windows_path "$ROOT_DIR")"
WINDOWS_BOT_DIR="$(to_windows_path "$BOT_DIR")"
WINDOWS_PYTHON_BIN="$(to_windows_path "$PYTHON_BIN")"
WINDOWS_UI_LOG="$(to_windows_path "$UI_LOG")"
WINDOWS_UI_ERR_LOG="$(to_windows_path "$UI_ERR_LOG")"

if [[ ! -f "$PYTHON_BIN" ]]; then
  echo "Python executable not found: $PYTHON_BIN"
  exit 1
fi

if [[ ! -f "$WINDOWS_PYTHON" ]]; then
  echo "PowerShell executable not found: $WINDOWS_PYTHON"
  exit 1
fi

if ! select_chainlit_port; then
  echo "Unable to find an open Chainlit port starting at ${REQUESTED_CHAINLIT_PORT}"
  exit 1
fi

if [[ "$CHAINLIT_PORT" != "$REQUESTED_CHAINLIT_PORT" ]]; then
  echo "Port ${REQUESTED_CHAINLIT_PORT} is unavailable, using ${CHAINLIT_PORT} instead"
fi

echo "Stopping existing Chainlit processes"
"$WINDOWS_PYTHON" -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -match 'python|chainlit' -and \$_.CommandLine -match 'chainlit run main.py' } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force }" >/dev/null 2>&1 || true

echo "Starting Chainlit UI on ${CHAINLIT_HOST}:${CHAINLIT_PORT}"
"$WINDOWS_PYTHON" -Command "\$env:DEBUG='false'; \$env:PYTHONPATH='${WINDOWS_ROOT_DIR}'; Start-Process -FilePath '${WINDOWS_PYTHON_BIN}' -ArgumentList '-m','chainlit','run','main.py','--host','${CHAINLIT_HOST}','--port','${CHAINLIT_PORT}' -WorkingDirectory '${WINDOWS_BOT_DIR}' -RedirectStandardOutput '${WINDOWS_UI_LOG}' -RedirectStandardError '${WINDOWS_UI_ERR_LOG}'" >/dev/null 2>&1

READY=0
for _ in $(seq 1 45); do
  if curl --silent --fail "$CHAINLIT_URL" >/dev/null 2>&1; then
    READY=1
    break
  fi
  sleep 2
done

if [[ "$READY" -eq 1 ]]; then
  print_summary "PASS"
  exit 0
fi

print_summary "FAIL"
exit 1
