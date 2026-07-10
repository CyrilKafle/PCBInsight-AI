// single_joint_controller.sv
//
// Phase 0 top level: wires spi_adc_reader -> p_controller -> pwm_generator
// into one closed-loop joint controller, driven by a free-running control-
// loop tick generated internally at CONTROL_FREQ_HZ.
//
// Default clocking matches the Tang Nano 9K's onboard 27 MHz oscillator.
// At those real-world frequencies a full ADC conversion (~144 system
// clocks) finishes in a tiny fraction of a single 540,000-cycle control
// period, so `tick` is gated on `!adc_busy` purely as cheap defensive
// practice, not because the margin is actually tight.

module single_joint_controller #(
    parameter int CLK_FREQ_HZ     = 27_000_000,
    parameter int CONTROL_FREQ_HZ = 50,
    parameter int ADC_CLK_DIV     = 4,
    parameter int KP_Q8           = 64
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [11:0] target_position,

    output logic        servo_pwm,

    output logic        adc_sclk,
    output logic        adc_cs_n,
    output logic        adc_mosi,
    input  logic        adc_miso
);

  localparam int TICK_PERIOD = CLK_FREQ_HZ / CONTROL_FREQ_HZ;
  localparam int TICK_W      = $clog2(TICK_PERIOD);

  logic [TICK_W-1:0] tick_counter;
  logic               tick;
  logic               adc_busy;
  logic               adc_data_valid;
  logic [11:0]        adc_data;
  logic [11:0]        command;
  logic               command_valid;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      tick_counter <= '0;
      tick         <= 1'b0;
    end else if (tick_counter == TICK_PERIOD - 1) begin
      tick_counter <= '0;
      tick         <= !adc_busy;
    end else begin
      tick_counter <= tick_counter + 1'b1;
      tick         <= 1'b0;
    end
  end

  spi_adc_reader #(
      .CLK_DIV(ADC_CLK_DIV)
  ) u_adc (
      .clk       (clk),
      .rst_n     (rst_n),
      .start     (tick),
      .busy      (adc_busy),
      .data_valid(adc_data_valid),
      .data      (adc_data),
      .sclk      (adc_sclk),
      .cs_n      (adc_cs_n),
      .mosi      (adc_mosi),
      .miso      (adc_miso)
  );

  p_controller #(
      .KP_Q8(KP_Q8)
  ) u_ctrl (
      .clk              (clk),
      .rst_n            (rst_n),
      .target_position  (target_position),
      .measured_position(adc_data),
      .measured_valid   (adc_data_valid),
      .command          (command),
      .command_valid    (command_valid)
  );

  pwm_generator #(
      .CLK_FREQ_HZ(CLK_FREQ_HZ)
  ) u_pwm (
      .clk     (clk),
      .rst_n   (rst_n),
      .position(command),
      .pwm_out (servo_pwm)
  );

endmodule
