#!/bin/sh
# Usage: scripts/package.sh NNN   -> runs tests + demo, writes runs/run-NNN, zips to OUT_DIR
set -e
N="${1:?run number, e.g. 001}"; OUT_DIR="${2:-/mnt/user-data/outputs}"
cd "$(dirname "$0")/.."
(python -m pytest -q 2>/dev/null || python scripts/minipytest.py) 2>&1 | tee "runs/run-$N-tests.txt" | tail -3
mkdir -p "runs/run-$N"; mv "runs/run-$N-tests.txt" "runs/run-$N/test_output.txt"
python scripts/demo_synthetic.py "runs/run-$N" > /dev/null
python -m privacyfirst.bench --out "runs/run-$N" --seeds 5 --frames 120 > /dev/null
python -m privacyfirst.bench.swapbench --out "runs/run-$N" --seeds 3 --frames 120 > /dev/null
python scripts/demo_swap.py "runs/run-$N" > /dev/null
python scripts/demo_two_pass.py "runs/run-$N" > /dev/null
if command -v tesseract >/dev/null; then python scripts/demo_context.py "runs/run-$N" > /dev/null; python -m privacyfirst.bench.contextbench --out "runs/run-$N" --seeds 4 > /dev/null; fi
find . -name __pycache__ -prune -exec rm -rf {} + ; rm -rf .pytest_cache
mkdir -p "$OUT_DIR"; rm -f "$OUT_DIR/PrivacyFirst-run-$N.zip"
(cd .. && zip -qr "$OUT_DIR/PrivacyFirst-run-$N.zip" PrivacyFirst -x '*/__pycache__/*' '*.pyc' '*/.pytest_cache/*' '*.egg-info/*')
echo "wrote $OUT_DIR/PrivacyFirst-run-$N.zip"
