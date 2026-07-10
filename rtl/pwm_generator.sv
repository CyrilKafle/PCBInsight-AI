// pwm_generator.sv
//
// Standard hobby-servo PWM: 50 Hz period (20 ms), 1-2 ms pulse width.
// `position` is a 12-bit target: 0 = fully CCW (1 ms pulse), 4095 = fully CW (2 ms pulse).
//
// Default CLK_FREQ_HZ matches the Tang Nano 9K's onboard 27 MHz oscillator.

module pwm_generator #(
    parameter int CLK_FREQ_HZ = 27_000_000,
    parameter int PWM_FREQ_HZ = 50
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [11:0] position,
    output logic        pwm_out
);

  localparam int PERIOD_CYCLES    = CLK_FREQ_HZ / PWM_FREQ_HZ;
  localparam int MIN_PULSE_CYCLES = CLK_FREQ_HZ / 1000;  // 1 ms
  localparam int MAX_PULSE_CYCLES = CLK_FREQ_HZ / 500;   // 2 ms
  localparam int PULSE_RANGE      = MAX_PULSE_CYCLES - MIN_PULSE_CYCLES;
  localparam int CTR_W            = $clog2(PERIOD_CYCLES);

  logic [CTR_W-1:0] counter;
  logic [CTR_W-1:0] pulse_width_cycles;

  // Pulse width is latched once per period (not recomputed mid-pulse) so a
  // `position` update never glitches a pulse that's already in flight.
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      counter            <= '0;
      pulse_width_cycles <= MIN_PULSE_CYCLES;
    end else if (counter == PERIOD_CYCLES - 1) begin
      counter <= '0;
      // >>12 (i.e. /4096) instead of /4095 keeps this a synthesizable shift
      // instead of a general divider; off by <1 cycle at full scale, negligible.
      // Assignment to the CTR_W-wide reg truncates the wider intermediate
      // sum automatically — safe here since the true result always fits.
      pulse_width_cycles <= MIN_PULSE_CYCLES + ((position * PULSE_RANGE) >> 12);
    end else begin
      counter <= counter + 1'b1;
    end
  end

  assign pwm_out = (counter < pulse_width_cycles);

endmodule
