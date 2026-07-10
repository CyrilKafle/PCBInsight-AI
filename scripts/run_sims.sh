#!/usr/bin/env bash
# Compiles and runs every Phase 0 testbench with Icarus Verilog, printing a
# pass/fail summary. Run from anywhere: ./scripts/run_sims.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RTL="$ROOT/rtl"
SIM="$ROOT/sim"
BUILD="$SIM/work"

mkdir -p "$BUILD"

PASS_COUNT=0
FAIL_COUNT=0
TOTAL=0

run_tb() {
  local name="$1"
  shift
  local sources=("$@")
  TOTAL=$((TOTAL + 1))

  echo "=== $name ==="
  if iverilog -g2012 -o "$BUILD/$name.vvp" "${sources[@]}"; then
    local out
    out="$(vvp "$BUILD/$name.vvp" 2>&1)"
    echo "$out"
    if echo "$out" | grep -q "ALL TESTS PASSED"; then
      PASS_COUNT=$((PASS_COUNT + 1))
    else
      FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
  else
    echo "COMPILE FAILED"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
  echo ""
}

run_tb "pwm_generator_tb" \
  "$RTL/pwm_generator.sv" "$SIM/pwm_generator_tb.sv"

run_tb "spi_adc_reader_tb" \
  "$RTL/spi_adc_reader.sv" "$SIM/mcp3208_model.sv" "$SIM/spi_adc_reader_tb.sv"

run_tb "p_controller_tb" \
  "$RTL/p_controller.sv" "$SIM/p_controller_tb.sv"

run_tb "single_joint_controller_tb" \
  "$RTL/pwm_generator.sv" "$RTL/spi_adc_reader.sv" "$RTL/p_controller.sv" \
  "$RTL/single_joint_controller.sv" "$SIM/mcp3208_model.sv" "$SIM/single_joint_controller_tb.sv"

echo "=== SUMMARY: $PASS_COUNT/$TOTAL testbenches passed ==="
[ "$FAIL_COUNT" -eq 0 ]
