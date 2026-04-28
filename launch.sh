#!/bin/bash
# TradeMind - One-Click Launcher
# Usage: ./launch.sh [host] [port]
#   ./launch.sh              → http://0.0.0.0:5000
#   ./launch.sh 127.0.0.1    → localhost only
#   ./launch.sh 0.0.0.0 8080 → custom port

PROJ="$(cd "$(dirname "$0")" && pwd)"
VENV="/home/guxiao/.hermes/stock-agent-venv/bin/python3"
HOST="${1:-0.0.0.0}"
PORT="${2:-5000}"

cd "$PROJ"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║        TradeMind Dashboard              ║"
echo "  ╠══════════════════════════════════════════╣"
echo "  ║  URL:  http://${HOST}:${PORT}/              ║"
echo "  ║  Ctrl+C to stop                         ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

exec "$VENV" web/app.py --host "$HOST" --port "$PORT"
