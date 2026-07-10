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
