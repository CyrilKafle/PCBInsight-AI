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

// spi_adc_reader.sv
//
// Bit-banged SPI master reading a 12-bit single-ended conversion from an
// MCP3208-class ADC, fixed to channel 0 for Phase 0. SPI Mode 0 shape:
// SCLK idles low, each bit gets a low half (setup) then a high half
// (sample), 5 command bits (start=1, sgl/diff=1, D2:D0=000) followed by
// 1 null bit and 12 data bits, MSB first.
//
// NOTE: this models the MCP3208 command/response *shape* but the exact edge
// timing has not been checked bit-for-bit against the MCP3208 datasheet —
// do that before real hardware bring-up in Phase 1. The behavioral ADC
// model in the testbench follows the same timing this master assumes, so a
// passing simulation proves internal consistency, not datasheet fidelity.

module spi_adc_reader #(
    parameter int CLK_DIV = 4  // system clocks per SPI half-bit-period
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        start,
    output logic        busy,
    output logic        data_valid,
    output logic [11:0] data,

    output logic        sclk,
    output logic        cs_n,
    output logic        mosi,
    input  logic        miso
);

  localparam logic [4:0] CMD        = 5'b11000;  // start, sgl/diff, ch=000
  localparam int          CMD_BITS   = 5;
  localparam int          NULL_BITS  = 1;
  localparam int          DATA_BITS  = 12;
  localparam int          TOTAL_BITS = CMD_BITS + NULL_BITS + DATA_BITS;

  typedef enum logic {
    IDLE,
    XFER
  } state_t;

  state_t                          state;
  logic [$clog2(CLK_DIV+1)-1:0]    div_cnt;
  logic                            sclk_phase;  // 0 = low half, 1 = high half
  logic [$clog2(TOTAL_BITS+1)-1:0] bit_cnt;
  logic [CMD_BITS-1:0]             cmd_shift;
  logic [DATA_BITS-1:0]            data_shift;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state      <= IDLE;
      cs_n       <= 1'b1;
      sclk       <= 1'b0;
      mosi       <= 1'b0;
      busy       <= 1'b0;
      data_valid <= 1'b0;
      data       <= '0;
      div_cnt    <= '0;
      sclk_phase <= 1'b0;
      bit_cnt    <= '0;
      cmd_shift  <= '0;
      data_shift <= '0;
    end else begin
      data_valid <= 1'b0;  // default: 1-cycle pulse

      case (state)
        IDLE: begin
          cs_n <= 1'b1;
          sclk <= 1'b0;
          busy <= 1'b0;
          if (start) begin
            state      <= XFER;
            cs_n       <= 1'b0;
            busy       <= 1'b1;
            div_cnt    <= '0;
            sclk_phase <= 1'b0;
            bit_cnt    <= '0;
            cmd_shift  <= CMD;
            mosi       <= CMD[CMD_BITS-1];  // first command bit, MSB first
          end
        end

        XFER: begin
          if (div_cnt == CLK_DIV - 1) begin
            div_cnt <= '0;

            if (sclk_phase == 1'b0) begin
              // End of low half: raise SCLK. This is the sample point.
              sclk       <= 1'b1;
              sclk_phase <= 1'b1;
              if (bit_cnt >= CMD_BITS + NULL_BITS) begin
                data_shift <= {data_shift[DATA_BITS-2:0], miso};
              end
            end else begin
              // End of high half: fall SCLK, advance to the next bit.
              sclk       <= 1'b0;
              sclk_phase <= 1'b0;
              bit_cnt    <= bit_cnt + 1'b1;

              if (bit_cnt + 1 < TOTAL_BITS) begin
                if (bit_cnt + 1 < CMD_BITS) begin
                  cmd_shift <= cmd_shift << 1;
                  mosi      <= cmd_shift[CMD_BITS-2];
                end else begin
                  mosi <= 1'b0;  // don't-care during null + data phase
                end
              end else begin
                // Last bit done: go straight back to IDLE in the same edge
                // that drops `busy` and raises `data_valid`, so a caller
                // that retriggers as soon as `busy` clears is never racing
                // an extra transition cycle.
                state      <= IDLE;
                cs_n       <= 1'b1;
                busy       <= 1'b0;
                data_valid <= 1'b1;
                data       <= data_shift;
              end
            end
          end else begin
            div_cnt <= div_cnt + 1'b1;
          end
        end

        default: state <= IDLE;
      endcase
    end
  end

endmodule

// p_controller.sv
//
// Discrete-time proportional position controller. Each time a new ADC
// reading arrives (`measured_valid` pulses), nudges the commanded position
// toward the target by a fraction (KP_Q8/256) of the current error:
//
//   command = measured_position + Kp * (target_position - measured_position)
//
// With 0 < Kp <= 1 this is a stable, monotonic (no-overshoot) approach to
// the target — the same shape as a discrete first-order low-pass filter.
// It's deliberately simple for Phase 0; a real PID (adding integral term to
// kill steady-state error, and derivative term to damp oscillation under
// load) is the natural Phase 2 upgrade once this is proven in hardware.

module p_controller #(
    parameter int KP_Q8 = 64  // proportional gain, Q8 fixed point (64/256 = 0.25)
) (
    input  logic        clk,
    input  logic        rst_n,
    input  logic [11:0] target_position,
    input  logic [11:0] measured_position,
    input  logic        measured_valid,  // pulse: a new ADC reading just arrived
    output logic [11:0] command,
    output logic        command_valid    // pulse: `command` just updated
);

  logic signed [13:0] error;        // target - measured, range -4095..4095
  logic signed [22:0] scaled_step;  // error * KP_Q8
  logic signed [13:0] step;         // scaled_step >>> 8
  logic signed [14:0] raw_command;  // measured + step, may fall outside [0,4095]

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      command       <= 12'd0;
      command_valid <= 1'b0;
    end else begin
      command_valid <= 1'b0;

      if (measured_valid) begin
        error       = $signed({1'b0, target_position}) - $signed({1'b0, measured_position});
        scaled_step = error * KP_Q8;
        step        = scaled_step >>> 8;
        raw_command = $signed({2'b00, measured_position}) + step;

        if (raw_command < 0) command <= 12'd0;
        else if (raw_command > 15'sd4095) command <= 12'd4095;
        else command <= raw_command[11:0];

        command_valid <= 1'b1;
      end
    end
  end

endmodule

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
