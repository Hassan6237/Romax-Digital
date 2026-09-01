#!/usr/bin/env bash
# ============================================================
# Romax Digital – Wallet Pass Creator
# Start script
# ============================================================
set -e

echo ""
echo "  ██████╗  ██████╗ ███╗   ███╗ █████╗ ██╗  ██╗"
echo "  ██╔══██╗██╔═══██╗████╗ ████║██╔══██╗╚██╗██╔╝"
echo "  ██████╔╝██║   ██║██╔████╔██║███████║ ╚███╔╝ "
echo "  ██╔══██╗██║   ██║██║╚██╔╝██║██╔══██║ ██╔██╗ "
echo "  ██║  ██║╚██████╔╝██║ ╚═╝ ██║██║  ██║██╔╝ ██╗"
echo "  ╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝"
echo ""
echo "  Romax Digital – Prototype"
echo "  ============================================================"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Please install Python 3.9+"
  exit 1
fi

# Install deps if needed
echo "  Checking dependencies..."
pip install -r requirements.txt --break-system-packages -q 2>/dev/null || \
pip install -r requirements.txt -q

echo "  Starting server on http://localhost:5000"
echo "  Press Ctrl+C to stop."
echo ""

python3 app.py
