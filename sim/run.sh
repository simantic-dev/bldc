#!/usr/bin/env bash
# Run the unmodified VESC firmware (hw 75_300, STM32F405RG) in the simulator, check the output, and draw the PNG.
# Needs a `sim` with the F405 timer-trigger and ADC-triple-mode model (pyrite#3515, not in released 0.10.4: see README),
# and python3 with matplotlib for the plot. Set SIM= to that binary.
# ELF: `make fw_75_300 ARM_SDK_PREFIX=arm-none-eabi- ULIBS="-lm -u _printf_float"` in the repo root, copy build/75_300/75_300.elf here
# as vesc_75_300.elf (committed already).
set -euo pipefail
cd "$(dirname "$0")"
SIM=${SIM:-sim}
PY=${PY:-python3}
REC=$(mktemp -d)
trap 'rm -rf "$REC"' EXIT
$SIM run --scenario scenario.yaml --ascii --record "$REC" 2>&1 | grep -v "newer sim" > run.log
grep -q "FWV .* hw=75_300" run.log && echo "PASS  COMM_FW_VERSION answered" || { echo "FAIL  no version reply"; exit 1; }
grep -qE "HardFault|panicked" run.log && { echo "FAIL  HardFault/panic"; exit 1; } || echo "PASS  no HardFault/panic"
$PY plot.py "$REC" vesc.png run.log | tee measured.txt
