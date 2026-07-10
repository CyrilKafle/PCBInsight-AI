// spi_adc_reader_tb.sv
//
// Self-checking testbench for spi_adc_reader. Wires the DUT to a behavioral
// mcp3208_model and checks that a full command/response cycle reads back
// several known 12-bit test values correctly.

`timescale 1ns / 1ps

module spi_adc_reader_tb;

  localparam int CLK_DIV = 4;

  logic        clk = 0;
  logic        rst_n;
  logic        start;
  logic        busy;
  logic        data_valid;
  logic [11:0] data;

  logic        sclk, cs_n, mosi, miso;
  logic [11:0] test_value;

  int          errors = 0;

  spi_adc_reader #(
      .CLK_DIV(CLK_DIV)
  ) dut (
      .clk       (clk),
      .rst_n     (rst_n),
      .start     (start),
      .busy      (busy),
      .data_valid(data_valid),
      .data      (data),
      .sclk      (sclk),
      .cs_n      (cs_n),
      .mosi      (mosi),
      .miso      (miso)
  );

  mcp3208_model adc_model (
      .sclk      (sclk),
      .cs_n      (cs_n),
      .mosi      (mosi),
      .test_value(test_value),
      .miso      (miso)
  );

  always #5 clk = ~clk;  // 100 MHz sim clock — timing is irrelevant here,
                          // only bit sequencing matters for this test.

  task automatic check_reading(logic [11:0] value, string label);
    test_value = value;
    start      = 1'b1;
    @(posedge clk);
    start = 1'b0;

    wait (data_valid === 1'b1);
    if (data === value) begin
      $display("PASS [%s] wrote test_value=%0d, read back data=%0d", label, value, data);
    end else begin
      $display("FAIL [%s] wrote test_value=%0d, read back data=%0d", label, value, data);
      errors++;
    end

    @(posedge clk);
    while (busy) @(posedge clk);
  endtask

  initial begin
    rst_n      = 0;
    start      = 0;
    test_value = 0;
    repeat (5) @(posedge clk);
    rst_n = 1;
    repeat (2) @(posedge clk);

    check_reading(12'h000, "zero");
    check_reading(12'hFFF, "max");
    check_reading(12'hA5A, "pattern");
    check_reading(12'd2048, "midscale");

    if (errors == 0) $display("SPI_ADC_READER_TB: ALL TESTS PASSED");
    else              $display("SPI_ADC_READER_TB: %0d TEST(S) FAILED", errors);

    $finish;
  end

  // Safety timeout in case a transfer never completes.
  initial begin
    #1_000_000;
    $display("SPI_ADC_READER_TB: TIMEOUT — a transfer never completed");
    $finish;
  end

endmodule
