#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
SCRIPT="${ROOT_DIR}/applocation/NeuroLink/scripts/collect_neurolink_memory_evidence.py"
PYTHON_BIN="${ROOT_DIR}/.venv/bin/python"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

grep -q -- "--overlay-config" "${SCRIPT}"
grep -q -- "--require-external-staging-evidence" "${SCRIPT}"

mkdir -p "${TMP_DIR}/build/neurolink_unit/zephyr" "${TMP_DIR}/memory-evidence"

cat >"${TMP_DIR}/build/neurolink_unit/zephyr/.config" <<'EOF'
CONFIG_MAIN_STACK_SIZE=18432
CONFIG_SYSTEM_WORKQUEUE_STACK_SIZE=5120
CONFIG_SHELL_STACK_SIZE=4096
CONFIG_HEAP_MEM_POOL_SIZE=53248
CONFIG_NET_PKT_RX_COUNT=20
CONFIG_NET_PKT_TX_COUNT=20
CONFIG_NET_BUF_RX_COUNT=48
CONFIG_NET_BUF_TX_COUNT=48
CONFIG_BOARD="dnesp32s3b"
CONFIG_BOARD_TARGET="dnesp32s3b/esp32s3/procpu"
CONFIG_BOARD_QUALIFIERS="esp32s3/procpu"
CONFIG_SOC="esp32s3"
CONFIG_SOC_SERIES_ESP32S3=y
CONFIG_ESP_SPIRAM=y
CONFIG_ESP_SPIRAM_HEAP_SIZE=2097152
CONFIG_ESP_WIFI_HEAP_SPIRAM=y
CONFIG_ESP32_WIFI_NET_ALLOC_SPIRAM=y
CONFIG_SHARED_MULTI_HEAP=y
CONFIG_LLEXT_HEAP_DYNAMIC=y
CONFIG_SYS_HEAP_RUNTIME_STATS=y
CONFIG_NEUROLINK_ZENOH_PICO_DEBUG_LEVEL=0
CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=24576
# CONFIG_NEUROLINK_ZENOH_PICO_DEBUG is not set
# CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER is not set
# CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER is not set
EOF

cat >"${TMP_DIR}/build/neurolink_unit/build_info.yml" <<'EOF'
board:
  name: dnesp32s3b
  qualifiers: esp32s3/procpu
version: 4.4.99
EOF

cat >"${TMP_DIR}/build/neurolink_unit/zephyr/zephyr.stat" <<'EOF'
Section Headers:
  [ 9] .iram0.vectors    PROGBITS        40374000 000218 000400 00  AX  0   0  4
  [10] .iram0.text       PROGBITS        40374400 000618 00fe98 00  AX  0   0  4
  [16] .dram0.data       PROGBITS        3fc948f0 010af0 004bb0 00  WA  0   0  8
  [36] .dram0.noinit     NOBITS          3fc99f70 016170 03fe58 00  WA  0   0 16
  [37] .dram0.bss        NOBITS          3fcd9dd0 016170 00e9c0 00  WA  0   0 16
  [41] .flash.rodata     PROGBITS        3c090000 0a0000 01460c 00   A  0   0 65536
  [61] .ext_ram.data     NOBITS          3c0b0000 0b5450 207420 00  WA  0   0 16
EOF

cat >"${TMP_DIR}/build.log" <<'EOF'
Memory region         Used Size  Region Size  %age Used
           IRAM:          66680 B      131072 B     50.87%
           DRAM:         395152 B      399104 B     99.01%
<inf> neurolink_unit: update heap snapshot stage=prepare:demo_app:start free=49152 allocated=8192 max_allocated=12288
<inf> app_runtime: app-runtime heap snapshot stage=load_file:after_alloc path=/mock/apps/demo_app.llext free=45056 allocated=12288 max_allocated=16384
EOF
printf '%b' '<inf> app_runtime: app-runtime ELF staging allocation path=/mock/apps/demo_app.llext bytes=40960 source=static provider=esp-spiram\033[0m
--- 1571 messages dropped ---
' >>"${TMP_DIR}/build.log"

output="$(${PYTHON_BIN} "${SCRIPT}" \
  --build-dir "${TMP_DIR}/build/neurolink_unit" \
  --output-dir "${TMP_DIR}/memory-evidence" \
  --build-log "${TMP_DIR}/build.log" \
  --require-runtime-evidence \
  --label test-baseline)"

[[ "${output}" == *"release_target=1.1.9"* ]] || {
  printf '%s\n' "${output}" >&2
  exit 1
}

json_file="${TMP_DIR}/memory-evidence/test-baseline.json"
summary_file="${TMP_DIR}/memory-evidence/test-baseline.summary.txt"
[[ -f "${json_file}" && -f "${summary_file}" ]] || {
  echo "expected evidence outputs were not created" >&2
  exit 1
}

${PYTHON_BIN} - "${json_file}" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
assert payload["config"]["CONFIG_HEAP_MEM_POOL_SIZE"] == 53248
assert payload["config"]["CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER"] == "n"
assert payload["config"]["CONFIG_NEUROLINK_APP_PREFER_PSRAM_ELF_BUFFER"] == "n"
assert payload["config"]["CONFIG_NEUROLINK_ZENOH_PICO_DEBUG"] == "n"
assert payload["config"]["CONFIG_NEUROLINK_ZENOH_PICO_DEBUG_LEVEL"] == 0
assert payload["config"]["CONFIG_LLEXT_HEAP_DYNAMIC"] == "y"
assert payload["platform"]["board"] == "dnesp32s3b"
assert payload["platform"]["soc"] == "esp32s3"
assert payload["memory_capability"]["provider"] == "esp-spiram"
assert payload["memory_capability"]["external_memory_configured"] is True
assert payload["memory_capability"]["external_heap_size_bytes"] == 2097152
assert payload["memory_capability"]["external_elf_staging_preferred"] is False
assert payload["section_totals"]["dram0"] == int("004bb0", 16) + int("03fe58", 16) + int("00e9c0", 16)
assert payload["build_memory_summary"][0]["region"] == "IRAM"
assert payload["build_memory_summary"][1]["used_bytes"] == 395152
assert payload["runtime_heap_snapshots"][0]["scope"] == "update"
assert payload["runtime_heap_snapshots"][0]["stage"] == "prepare:demo_app:start"
assert payload["runtime_heap_snapshots"][1]["scope"] == "app-runtime"
assert payload["runtime_heap_snapshots"][1]["path"] == "/mock/apps/demo_app.llext"
assert payload["runtime_staging_allocations"][0]["path"] == "/mock/apps/demo_app.llext"
assert payload["runtime_staging_allocations"][0]["size_bytes"] == 40960
assert payload["runtime_staging_allocations"][0]["source"] == "static"
assert payload["runtime_staging_allocations"][0]["provider"] == "esp-spiram"
assert payload["runtime_drop_notices"][0]["count"] == 1571
assert payload["runtime_drop_notices"][0]["interpretation"] == "zenoh_runtime_pressure_notice_not_evidence_loss"
assert payload["runtime_fatal_exceptions"] == []
assert payload["runtime_evidence_gate"]["required"] is True
assert payload["runtime_evidence_gate"]["passed"] is True
assert payload["runtime_evidence_gate"]["missing"] == []
assert payload["external_staging_candidate_gate"]["required"] is False
assert payload["external_staging_candidate_gate"]["passed"] is False
assert payload["external_staging_candidate_gate"]["missing"] == [
  "external_staging_preference",
  "external_staging_allocation",
]
PY

grep -q "CONFIG_NEUROLINK_APP_STATIC_ELF_BUFFER_SIZE=24576" "${summary_file}"
grep -q "CONFIG_LLEXT_HEAP_DYNAMIC=y" "${summary_file}"
grep -q "CONFIG_NEUROLINK_ZENOH_PICO_DEBUG=n" "${summary_file}"
grep -q "CONFIG_NEUROLINK_ZENOH_PICO_DEBUG_LEVEL=0" "${summary_file}"
grep -q "\[platform\]" "${summary_file}"
grep -q "board=dnesp32s3b" "${summary_file}"
grep -q "\[memory_capability\]" "${summary_file}"
grep -q "provider=esp-spiram" "${summary_file}"
grep -q "external_heap_size_bytes=2097152" "${summary_file}"
grep -q "update:prepare:demo_app:start:path=-:free=49152:allocated=8192:max_allocated=12288" "${summary_file}"
grep -q "app-runtime:load_file:after_alloc:path=/mock/apps/demo_app.llext:free=45056:allocated=12288:max_allocated=16384" "${summary_file}"
grep -q "path=/mock/apps/demo_app.llext:bytes=40960:source=static:provider=esp-spiram" "${summary_file}"
grep -q "\[runtime_drop_notices\]" "${summary_file}"
grep -q "count=1" "${summary_file}"
grep -q "total_dropped_messages=1571" "${summary_file}"
grep -q "interpretation=zenoh_runtime_pressure_notice_not_evidence_loss" "${summary_file}"
grep -q "\[runtime_fatal_exceptions\]" "${summary_file}"
grep -q "not_available=no fatal exceptions found in supplied logs" "${summary_file}"
grep -q "\[runtime_evidence_gate\]" "${summary_file}"
grep -q "required=True" "${summary_file}"
grep -q "passed=True" "${summary_file}"
grep -q "missing=-" "${summary_file}"
grep -q "\[external_staging_candidate_gate\]" "${summary_file}"
grep -q "external_staging_preferred=False" "${summary_file}"
grep -q "has_external_staging_allocation=False" "${summary_file}"

sed \
  -e 's/# CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER is not set/CONFIG_NEUROLINK_APP_PREFER_EXTERNAL_ELF_BUFFER=y/' \
  "${TMP_DIR}/build/neurolink_unit/zephyr/.config" \
  >"${TMP_DIR}/build/neurolink_unit/zephyr/.config.external"
mv "${TMP_DIR}/build/neurolink_unit/zephyr/.config.external" \
  "${TMP_DIR}/build/neurolink_unit/zephyr/.config"

cat >"${TMP_DIR}/external-build.log" <<'EOF'
Memory region         Used Size  Region Size  %age Used
           IRAM:          66680 B      131072 B     50.87%
           DRAM:         395152 B      399104 B     99.01%
<inf> neurolink_unit: update heap snapshot stage=prepare:demo_app:start free=49152 allocated=8192 max_allocated=12288
<inf> app_runtime: app-runtime heap snapshot stage=load_file:after_alloc path=/mock/apps/demo_app.llext free=53248 allocated=4096 max_allocated=8192
<inf> app_runtime: app-runtime ELF staging allocation path=/mock/apps/demo_app.llext bytes=40960 source=external provider=esp-spiram
<err> os:  ** FATAL EXCEPTION
<err> os:  ** CPU 0 EXCCAUSE 2 (instr fetch error)
<err> os:  **  PC 0x3c0c7718 VADDR 0x3c0c7718
EOF

external_output="$(${PYTHON_BIN} "${SCRIPT}" \
  --build-dir "${TMP_DIR}/build/neurolink_unit" \
  --output-dir "${TMP_DIR}/memory-evidence" \
  --build-log "${TMP_DIR}/external-build.log" \
  --require-runtime-evidence \
  --require-external-staging-evidence \
  --label test-external-candidate)"

[[ "${external_output}" == *"release_target=1.1.9"* ]] || {
  printf '%s\n' "${external_output}" >&2
  exit 1
}

${PYTHON_BIN} - "${TMP_DIR}/memory-evidence/test-external-candidate.json" <<'PY'
import json
import sys

payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
assert payload["memory_capability"]["external_elf_staging_preferred"] is True
assert payload["runtime_staging_allocations"][0]["source"] == "external"
assert payload["external_staging_candidate_gate"]["required"] is True
assert payload["external_staging_candidate_gate"]["passed"] is True
assert payload["external_staging_candidate_gate"]["missing"] == []
assert payload["external_staging_candidate_gate"]["providers"] == ["esp-spiram"]
assert payload["runtime_fatal_exceptions"][0]["cause"] == 2
assert payload["runtime_fatal_exceptions"][0]["cause_detail"] == "instr fetch error"
assert payload["runtime_fatal_exceptions"][0]["pc"] == "0x3c0c7718"
PY

grep -q "\[external_staging_candidate_gate\]" "${TMP_DIR}/memory-evidence/test-external-candidate.summary.txt"
grep -q "required=True" "${TMP_DIR}/memory-evidence/test-external-candidate.summary.txt"
grep -q "passed=True" "${TMP_DIR}/memory-evidence/test-external-candidate.summary.txt"
grep -q "providers=esp-spiram" "${TMP_DIR}/memory-evidence/test-external-candidate.summary.txt"
grep -q "\[runtime_fatal_exceptions\]" "${TMP_DIR}/memory-evidence/test-external-candidate.summary.txt"
grep -q "detail=instr fetch error" "${TMP_DIR}/memory-evidence/test-external-candidate.summary.txt"

cat >"${TMP_DIR}/build-without-runtime.log" <<'EOF'
Memory region         Used Size  Region Size  %age Used
           IRAM:          66680 B      131072 B     50.87%
           DRAM:         395152 B      399104 B     99.01%
EOF

set +e
missing_output="$(${PYTHON_BIN} "${SCRIPT}" \
  --build-dir "${TMP_DIR}/build/neurolink_unit" \
  --output-dir "${TMP_DIR}/memory-evidence" \
  --build-log "${TMP_DIR}/build-without-runtime.log" \
  --require-runtime-evidence \
  --label test-missing-runtime 2>&1)"
missing_ret=$?
set -e

[[ ${missing_ret} -eq 2 ]] || {
  printf 'expected missing runtime evidence failure, got %d\n%s\n' "${missing_ret}" "${missing_output}" >&2
  exit 1
}
[[ "${missing_output}" == *"runtime_evidence_gate=failed"* ]] || {
  printf '%s\n' "${missing_output}" >&2
  exit 1
}
[[ "${missing_output}" == *"update_heap_snapshot"* ]] || {
  printf '%s\n' "${missing_output}" >&2
  exit 1
}
grep -q "passed=False" "${TMP_DIR}/memory-evidence/test-missing-runtime.summary.txt"
grep -q "missing=update_heap_snapshot,app_runtime_heap_snapshot,staging_allocation" "${TMP_DIR}/memory-evidence/test-missing-runtime.summary.txt"

echo "test_collect_neurolink_memory_evidence.sh: PASS"
