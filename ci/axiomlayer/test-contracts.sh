#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
  echo "usage: test-contracts.sh HARNESS SOURCE [CONTROL]" >&2
  exit 2
fi

harness=$(cd "$1" && pwd)
source_repo=$(cd "$2" && pwd)

python3 "$harness/ci/axiomlayer/verify_workflows.py" --root "$harness"
pin_args=(
  --manifest "$harness/.github/axiomlayer/fleet-pin.json"
  --source "$source_repo"
)
if [[ $# -eq 3 ]]; then
  control=$(cd "$3" && pwd)
  pin_args+=(--control "$control")
fi
python3 "$harness/ci/axiomlayer/verify_fleet_pin.py" "${pin_args[@]}"

temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT
cp -R "$harness/.github" "$temporary/.github"
printf '\npermissions:\n  contents: write\n' >> "$temporary/.github/workflows/fleet-integration.yml"
if python3 "$harness/ci/axiomlayer/verify_workflows.py" --root "$temporary" >/dev/null 2>&1; then
  echo "workflow verifier accepted a write-capable mutation" >&2
  exit 1
fi

cp "$harness/.github/axiomlayer/fleet-pin.json" "$temporary/tampered-pin.json"
python3 - "$temporary/tampered-pin.json" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
value = json.loads(path.read_text())
value["fleetPin"]["version"] = "0.0.0-tampered"
path.write_text(json.dumps(value, indent=2) + "\n")
PY
if python3 "$harness/ci/axiomlayer/verify_fleet_pin.py" \
  --manifest "$temporary/tampered-pin.json" \
  --source "$source_repo" >/dev/null 2>&1; then
  echo "fleet-pin verifier accepted a mutated version" >&2
  exit 1
fi

echo "tamper_refusal=verified"
