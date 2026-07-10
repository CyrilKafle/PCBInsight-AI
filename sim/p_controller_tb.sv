// p_controller_tb.sv
//
// Two checks:
//  1. Exact-math: for known (target, measured) pairs, the computed command
//     must match the formula independently re-derived in the testbench.
//  2. Closed-loop convergence: driving the controller's output through a
//     simple lagging "plant" model (simulating a servo settling toward
//     wherever it's commanded) must converge to the target within N ticks.

`timescale 1ns / 1ps

module p_controller_tb;

  localparam int KP_Q8 = 64;  // 0.25

  logic        clk = 0;
  logic        rst_n;
  logic [11:0] target_position;
  logic [11:0] measured_position;
  logic        measured_valid;
  logic [11:0] command;
  logic        command_valid;

  int          errors = 0;

  p_controller #(
      .KP_Q8(KP_Q8)
  ) dut (
      .clk              (clk),
      .rst_n            (rst_n),
      .target_position  (target_position),
      .measured_position(measured_position),
      .measured_valid   (measured_valid),
      .command          (command),
      .command_valid    (command_valid)
  );

  always #5 clk = ~clk;

  function automatic int expected_command(int target, int measured);
    int error, step, raw;
    error = target - measured;
    step  = (error * KP_Q8) >>> 8;
    raw   = measured + step;
    if (raw < 0) return 0;
    if (raw > 4095) return 4095;
    return raw;
  endfunction

  task automatic check_step(int target, int measured, string label);
    int exp_cmd;
    target_position   = target[11:0];
    measured_position = measured[11:0];
    measured_valid    = 1'b1;
    @(posedge clk);
    measured_valid = 1'b0;
    wait (command_valid === 1'b1);
    exp_cmd = expected_command(target, measured);
    if (command === exp_cmd[11:0]) begin
      $display("PASS [%s] target=%0d measured=%0d -> command=%0d (expected %0d)",
                label, target, measured, command, exp_cmd);
    end else begin
      $display("FAIL [%s] target=%0d measured=%0d -> command=%0d (expected %0d)",
                label, target, measured, command, exp_cmd);
      errors++;
    end
    @(posedge clk);
  endtask

  // Simulates the physical joint settling toward whatever position was just
  // commanded, with lag (>>2 = moves 1/4 of the remaining distance per
  // tick) — a stand-in for real servo + mechanical response time.
  // Tolerance and tick count are not arbitrary: traced by hand (see
  // docs/PHASE0_NOTES.md) — a pure P-controller combined with integer
  // (fixed-point) truncation in both this controller and the plant model
  // converges smoothly but settles into a small, *permanent* steady-state
  // gap once the computed correction rounds to zero (~15/4096 counts,
  // ~0.4% of full range, reached by ~100 ticks here). That's expected
  // behavior for P-only control, not a bug — eliminating it is exactly
  // what the integral term in a full PID controller is for, which is the
  // planned Phase 2 upgrade. 150 ticks and a +/-25 tolerance give margin
  // above the observed ~15-count settled gap without masking a real
  // divergence bug.
  localparam int CONVERGENCE_TICKS   = 150;
  localparam int CONVERGENCE_TOLERANCE = 25;

  task automatic run_convergence_test(int target_val, int start_measured, string label);
    int plant_measured;
    int tick;
    int cmd;
    plant_measured = start_measured;

    for (tick = 0; tick < CONVERGENCE_TICKS; tick++) begin
      target_position   = target_val[11:0];
      measured_position = plant_measured[11:0];
      measured_valid    = 1'b1;
      @(posedge clk);
      measured_valid = 1'b0;
      wait (command_valid === 1'b1);
      cmd = command;
      @(posedge clk);

      // Plant settles 1/4 of the way toward the new command each tick.
      plant_measured = plant_measured + ((cmd - plant_measured) >>> 2);
    end

    if ((plant_measured - target_val) >= -CONVERGENCE_TOLERANCE &&
        (plant_measured - target_val) <= CONVERGENCE_TOLERANCE) begin
      $display("PASS [%s] converged: measured=%0d target=%0d after %0d ticks",
                label, plant_measured, target_val, CONVERGENCE_TICKS);
    end else begin
      $display("FAIL [%s] did NOT converge: measured=%0d target=%0d after %0d ticks",
                label, plant_measured, target_val, CONVERGENCE_TICKS);
      errors++;
    end
  endtask

  initial begin
    rst_n           = 0;
    target_position = 0;
    measured_position = 0;
    measured_valid  = 0;
    repeat (5) @(posedge clk);
    rst_n = 1;
    repeat (2) @(posedge clk);

    // Exact-math checks.
    check_step(3000, 1000, "rising");
    check_step(1000, 3000, "falling");
    check_step(2048, 2048, "at_target");
    check_step(4095, 0,    "full_range");

    // Closed-loop convergence checks.
    run_convergence_test(3000,  500, "converge_up");
    run_convergence_test(500,  3800, "converge_down");
    run_convergence_test(2048, 2048, "already_there");

    if (errors == 0) $display("P_CONTROLLER_TB: ALL TESTS PASSED");
    else              $display("P_CONTROLLER_TB: %0d TEST(S) FAILED", errors);

    $finish;
  end

endmodule
