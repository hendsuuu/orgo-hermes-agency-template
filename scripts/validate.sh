#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
required=(
  README.md
  config/.env.example
  config/config.template.yaml
  orgo/agency-base.template.yaml
  control-plane/contracts/task.schema.json
  slack/intake-contract.md
)
for item in "${required[@]}"; do
  [[ -f "$ROOT/$item" ]] || { echo "Missing required file: $item" >&2; exit 1; }
done

python3 - "$ROOT" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
json.loads((root / 'control-plane/contracts/task.schema.json').read_text())
try:
    import yaml
except ModuleNotFoundError:
    print('PyYAML unavailable; skipped YAML syntax validation')
else:
    for relative in ('config/config.template.yaml', 'orgo/agency-base.template.yaml', 'slack/routing.template.yaml'):
        yaml.safe_load((root / relative).read_text())
print('Template validation passed')
PY

python3 -m py_compile "$ROOT"/control-plane/adapter/*.py \
  && echo "Adapter modules compile"

( cd "$ROOT/control-plane" && python3 -m adapter.selftest )
