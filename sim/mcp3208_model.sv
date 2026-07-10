// mcp3208_model.sv
//
// Minimal behavioral stand-in for an MCP3208 ADC, used only in simulation.
// Drives `miso` with `test_value`'s bits (MSB first) at the same bit
// positions spi_adc_reader expects: 5 command bits + 1 null bit are ignored,
// then bits 6-17 (0-indexed) carry the 12 data bits.

module mcp3208_model (
    input  logic        sclk,
    input  logic        cs_n,
    input  logic        mosi,
    input  logic [11:0] test_value,
    output logic        miso
);

  int bit_idx;

  always @(negedge cs_n) begin
    bit_idx = 0;
  end

  always @(negedge sclk) begin
    if (!cs_n) bit_idx = bit_idx + 1;
  end

  assign miso = (!cs_n && bit_idx >= 6 && bit_idx <= 17) ? test_value[17-bit_idx] : 1'b0;

endmodule
