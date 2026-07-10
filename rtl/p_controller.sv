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
