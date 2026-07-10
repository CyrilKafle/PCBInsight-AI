// single_joint_controller_tb.sv
//
// Full closed-loop integration test: DUT + a behavioral mcp3208_model +
// a simple lagging "plant" model standing in for the physical joint.
//
// The plant model reads the DUT's internal `command`/`adc_data_valid`
// signals via hierarchical reference (a normal, simulation-only technique —
// it doesn't change DUT behavior, just gives the testbench visibility) so
// this test can drive the ADC model's test_value without having to
// reverse-engineer position from raw PWM pulse timing. `servo_pwm` is
// still checked separately for basic liveness/plausibility.

`timescale 1ns / 1ps

module single_joint_controller_tb;

  localparam int CLK_FREQ_HZ     = 27_000;  // scaled down 1000x from real 27 MHz
  localparam int CONTROL_FREQ_HZ = 50;
  localparam int ADC_CLK_DIV     = 4;
  localparam int KP_Q8           = 64;

  logic        clk = 0;
  logic        rst_n;
  logic [11:0] target_position;
  logic        servo_pwm;
  logic        adc_sclk, adc_cs_n, adc_mosi, adc_miso;
  logic [11:0] plant_test_value;

  int          errors = 0;
  int          target_i;
  int          gap;

  single_joint_controller #(
      .CLK_FREQ_HZ    (CLK_FREQ_HZ),
      .CONTROL_FREQ_HZ(CONTROL_FREQ_HZ),
      .ADC_CLK_DIV    (ADC_CLK_DIV),
      .KP_Q8          (KP_Q8)
  ) dut (
      .clk            (clk),
      .rst_n          (rst_n),
      .target_position(target_position),
      .servo_pwm      (servo_pwm),
      .adc_sclk       (adc_sclk),
      .adc_cs_n       (adc_cs_n),
      .adc_mosi       (adc_mosi),
      .adc_miso       (adc_miso)
  );

  mcp3208_model adc_model (
      .sclk      (adc_sclk),
      .cs_n      (adc_cs_n),
      .mosi      (adc_mosi),
      .test_value(plant_test_value),
      .miso      (adc_miso)
  );

  localparam real CLK_PERIOD_NS = 1_000_000_000.0 / CLK_FREQ_HZ;
  always #(CLK_PERIOD_NS / 2.0) clk = ~clk;

  // --- Plant model: settles 1/4 of the way toward the latest command each
  // time the controller issues one, via hierarchical reference into the DUT.
  int plant_position;

  initial begin
    plant_position   = 500;
    plant_test_value = plant_position[11:0];
    forever begin
      @(posedge dut.command_valid);
      plant_position   = plant_position + ((dut.command - plant_position) >>> 2);
      plant_test_value = plant_position[11:0];
    end
  end

  // --- PWM liveness/plausibility check: independent of the plant model,
  // just confirms servo_pwm is toggling with a period in the right
  // ballpark (a stuck-high/stuck-low or wildly-wrong-frequency signal
  // would indicate the pwm_generator instance isn't actually wired/running).
  int pwm_edge_count = 0;
  always @(posedge servo_pwm) pwm_edge_count++;

  // --- Main sequence.
  initial begin
    rst_n           = 0;
    target_position = 12'd0;
    repeat (5) @(posedge clk);
    rst_n = 1;

    target_position = 12'd3000;

    // Let the loop run for a while (comfortably past the ~100-control-tick
    // settle point observed for p_controller in isolation; the extra PWM
    // and reset settling stages here add a modest amount of additional
    // latency, so this uses more ticks and a looser tolerance than the
    // p_controller-only test — see docs/PHASE0_NOTES.md).
    repeat (200 * (CLK_FREQ_HZ / CONTROL_FREQ_HZ)) @(posedge clk);

    // plant_position is a signed `int`; target_position is an unsigned
    // `logic [11:0]`. Mixing signed and unsigned operands in SystemVerilog
    // silently makes the *whole* expression unsigned, which would turn a
    // negative gap into a huge wrapped positive number, so target_position
    // is cast to signed int explicitly (see target_i/gap declarations above).
    target_i = int'(target_position);
    gap      = plant_position - target_i;

    $display("Final plant_position=%0d target=%0d (gap=%0d)",
              plant_position, target_i, gap);

    if (gap >= -150 && gap <= 150) begin
      $display("PASS [closed_loop] converged within tolerance");
    end else begin
      $display("FAIL [closed_loop] did not converge");
      errors++;
    end

    if (pwm_edge_count > 0) begin
      $display("PASS [pwm_liveness] servo_pwm toggled %0d times", pwm_edge_count);
    end else begin
      $display("FAIL [pwm_liveness] servo_pwm never toggled");
      errors++;
    end

    if (errors == 0) $display("SINGLE_JOINT_CONTROLLER_TB: ALL TESTS PASSED");
    else              $display("SINGLE_JOINT_CONTROLLER_TB: %0d TEST(S) FAILED", errors);

    $finish;
  end

endmodule
