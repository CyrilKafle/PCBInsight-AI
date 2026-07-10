// pwm_generator_tb.sv
//
// Self-checking testbench for pwm_generator. Uses a 1000x-scaled-down clock
// (27 kHz instead of 27 MHz) so the same period/pulse-width ratios hold but
// simulation finishes in milliseconds instead of seconds of wall-clock time.

`timescale 1ns / 1ps

module pwm_generator_tb;

  localparam int CLK_FREQ_HZ = 27_000;  // scaled down 1000x from real 27 MHz
  localparam int PWM_FREQ_HZ = 50;

  logic        clk = 0;
  logic        rst_n;
  logic [11:0] position;
  logic        pwm_out;

  int          errors = 0;

  pwm_generator #(
      .CLK_FREQ_HZ(CLK_FREQ_HZ),
      .PWM_FREQ_HZ(PWM_FREQ_HZ)
  ) dut (
      .clk     (clk),
      .rst_n   (rst_n),
      .position(position),
      .pwm_out (pwm_out)
  );

  localparam real CLK_PERIOD_NS = 1_000_000_000.0 / CLK_FREQ_HZ;
  always #(CLK_PERIOD_NS / 2.0) clk = ~clk;

  localparam int PERIOD_CYCLES    = CLK_FREQ_HZ / PWM_FREQ_HZ;  // 540
  localparam int MIN_PULSE_CYCLES = CLK_FREQ_HZ / 1000;         // 27  (1 ms)
  localparam int MAX_PULSE_CYCLES = CLK_FREQ_HZ / 500;          // 54  (2 ms)
  localparam int PULSE_RANGE      = MAX_PULSE_CYCLES - MIN_PULSE_CYCLES;

  function automatic int expected_high_cycles(int pos);
    return MIN_PULSE_CYCLES + ((pos * PULSE_RANGE) >> 12);
  endfunction

  // Samples exactly one PWM period, starting from a rising edge of pwm_out,
  // and returns how many of those cycles pwm_out was high.
  logic prev_pwm;
  task automatic sample_one_period(output int high_count);
    int i;
    do begin
      prev_pwm = pwm_out;
      @(posedge clk);
    end while (!(prev_pwm === 1'b0 && pwm_out === 1'b1));

    high_count = 1;  // the edge-aligned cycle itself is high
    for (i = 0; i < PERIOD_CYCLES - 1; i++) begin
      @(posedge clk);
      if (pwm_out) high_count++;
    end
  endtask

  task automatic run_case(logic [11:0] pos, string label);
    int high_count;
    int exp_high;
    position = pos;
    repeat (PERIOD_CYCLES) @(posedge clk);  // let the new position latch in
    sample_one_period(high_count);
    exp_high = expected_high_cycles(pos);
    if (high_count == exp_high) begin
      $display("PASS [%s] position=%0d -> high_cycles=%0d (expected %0d)",
                label, pos, high_count, exp_high);
    end else begin
      $display("FAIL [%s] position=%0d -> high_cycles=%0d (expected %0d)",
                label, pos, high_count, exp_high);
      errors++;
    end
  endtask

  initial begin
    rst_n    = 0;
    position = 0;
    repeat (5) @(posedge clk);
    rst_n = 1;

    run_case(12'd0,    "min");
    run_case(12'd2048, "mid");
    run_case(12'd4095, "max");

    if (errors == 0) $display("PWM_GENERATOR_TB: ALL TESTS PASSED");
    else              $display("PWM_GENERATOR_TB: %0d TEST(S) FAILED", errors);

    $finish;
  end

endmodule
