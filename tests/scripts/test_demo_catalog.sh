#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
CATALOG_FILE="${ROOT_DIR}/applocation/NeuroLink/subprojects/demo_catalog.json"

[[ -f "${CATALOG_FILE}" ]] || {
  echo "missing demo catalog: ${CATALOG_FILE}" >&2
  exit 1
}

python3 - <<'PY' "${CATALOG_FILE}"
import json
import sys
from pathlib import Path

catalog_path = Path(sys.argv[1])
payload = json.loads(catalog_path.read_text(encoding="utf-8"))

assert payload["schema_version"] == "1.1.10-demo-catalog-v1"
assert payload["release_series"] == "1.1.10"
assert payload["status"] == "closed"

entries = payload["entries"]
assert isinstance(entries, list)
assert len(entries) == 8

expected_ids = {
    "neuro_demo_i2c",
    "neuro_demo_spi",
    "neuro_demo_gpio",
    "neuro_demo_uart",
    "neuro_demo_adc_pwm",
    "neuro_demo_net_event",
    "neuro_demo_net_udp",
    "neuro_demo_integrated",
}

found_ids = {entry["app_id"] for entry in entries}
assert found_ids == expected_ids
assert "neuro_unit_app" not in found_ids

allowed_categories = {"hardware", "network", "integrated"}
allowed_status = {"planned", "candidate", "implemented_local", "deferred_next_release"}
for entry in entries:
    assert entry["category"] in allowed_categories
    assert entry["status"] in allowed_status
    assert entry["artifact"].endswith(f"{entry['app_id']}.llext")
    assert entry["source_dir"].endswith(entry["app_id"])
    assert "capability" in entry["commands"]
    assert len(entry["required_capabilities"]) >= 1
    assert len(entry["manifest_capabilities"]) >= 1
    assert isinstance(entry["hardware_required"], bool)
PY

echo "test_demo_catalog.sh: PASS"