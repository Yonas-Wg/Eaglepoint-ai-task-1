#!/usr/bin/env bash
set -euo pipefail

echo "Running unit tests"
PYTHONPATH=backend python -m pytest -q unit_tests

echo "Running API tests"
python -m pytest -q API_tests

echo "All tests passed"
