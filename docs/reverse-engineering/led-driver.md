# Physical LED output

## Register and interrupt evidence

| Source | Firmware evidence | Role and confidence |
|---|---|---|
| TIMER1, IRQ 9 | Vector `0x64 = 0x52B1`, base `0x40010100` from `0x538C`, 1500-Hz target from `0x5398` through `0x530C → 0x5824` | Starts the next LED bank at `0x52C4 → 0x3A18`. High |
| TIMER2, IRQ 10 | Vector `0x68 = 0x52CB`, base `0x40110000`, 1000-Hz target at `0x531E–0x5328` | Sets scan-ready via `0x52DE → 0x4BDA` and foreground `0x4C40` consumes it. High |
| TIMER3, IRQ 11 | Vector `0x6C = 0x52E5`, base `0x40110100`, 1000-Hz target at `0x5338–0x5340` | Increments software timer elapsed count at `0x5746`, serviced via `0x57D6`. High |
| SPI0, IRQ 14 | Vector `0x78 = 0x3661`, base `0x40030000` through literal `0x38F8`, enables/pending clears via `0x3644/0x3652` | Shifts LED data and implements per-triplet latch sequences. High |
| USBD, IRQ 23 | Vector `0x9C = 0x9E01`, registers in the `0x40060000` block, enable at `0x93B0` | USB setup/status and report service. High |
| PWM0 | Base `0x40040000` at `0x3ADC`, channel 1 setup via `0x514C` at `0x38BE/0x39DE` | Requests 2 MHz and duty parameter 5 in normal output. Likely grayscale clock. High setup, medium signal role |

Peripheral and IRQ naming cross-checked with the [NUC1261 BSP header](https://raw.githubusercontent.com/OpenNuvoton/NUC1261BSP/master/Library/Device/Nuvoton/NUC1261/Include/NUC1261.h).

## Row and serial sequence

**High.** `0x37A0` initializes SPI0 via `0x4E38` with a 15 MHz target (`0x3A14`) and a 32-bit initial configuration. `0x3A18` skips while `0x200027A8+0` is busy, advances bank modulo five, consumes pending at rollover, and queues the first triplet. The output index begins at zero. `0x3660` checks TX FIFO empty (status bit 16 at SPI0 +0x14), manipulates SPI data width and pin multiplexing, and stages the remaining entries through index 14.

At `0x3720–0x372A` the active frame is loaded into three state halfwords. SPI TX at `0x40030020` receives a 32-bit word containing blue in its upper half and green in its lower half. The next phase transmits 15 bits from red shifted right one (`0x367C–0x368C`), then GPIO writes supply the latch-edge data bit (`0x3696–0x36C8`). The Thumb code tests red with mask `0x8000` at `0x36B2–0x36C0`. SPI shifts the low 15 bits of `red >> 1`, and the GPIO data bit repeats red bit 15. If the sink samples that latch-edge bit as the final grayscale bit, the reconstructed red word is `(red & 0xFFFE) | (red >> 15)`. The firmware bit selection is high confidence. The sink interpretation needs bus capture. GPIO per-pin words at `0x50004280`, +8, +12 correspond to PC0, PC2 and PC3. Their transition pattern is consistent with DCLK, LE and serial data respectively. The code pulses PC0 with PC2 asserted during the last bit. At row end `0x3766–0x377C` there are two extra clocks with PC2 low, then three with PC2 high.

**High.** Row select order is PC6, PC5, PD7, PD15, PD14 from the five descriptors at `0x200025CC`. The prior row is deasserted when index 14 is queued (`0x3742–0x3762`); the new row is asserted after the final latch sequence (`0x377E–0x379C`). The blanking byte at driver state +9 causes zero RGB to be queued without changing frame content. `0x4440` calls `0x3F92` around some flash jobs, and `0x3914/0x39CC` reconfigure driver runtime during lifecycle changes.

**Medium.** This SPI-plus-GPIO sequence is consistent with the supplied MBI5043GP driver. The component has a 16-bit serial grayscale path and internal scrambled PWM. The exact PCB chain length, output pin mapping, pulse timing on the wire, and effective grayscale response require passive measurements. PWM duty setup is a property of clock generation. External brightness should multiply frame values and keep this hardware setup stock. [Macroblock MBI5043 datasheet](https://www.mblock.com.tw/upload/Datasheet/LED%20Driver%20IC/MBI5043/MBI5043%20Preliminary%20Datasheet%20VA.00-EN.pdf)

## Rates and capacity

**High configuration, medium real-time estimate.** `0x5824` configures the timer from the selected clock and integer prescale/compare. Clock initialization at `0x94CE` sets the three TIMER1–3 source selectors to zero via `0x5518`. The source-frequency table at `0x58F4` maps selector zero to 12 MHz. The timer math gives a divide-by-one prescaler and compare 8000 for TIMER1, with compare 12000 for TIMER2/3. The row target implies roughly 667 µs per bank and 3.33 ms per five-bank sweep, or ~300 full scans/s if transfers finish on time. It is also the nominal ceiling on page presentation. The actual period, skipped busy ticks, scan jitter, and optical PWM refresh are separate quantities. No measurements were made. Nominal line time for 15×48 grayscale bits at 15 MHz is ~48 µs per bank; actual SPI rate is divider-dependent and IRQ/GPIO turnaround and final latch clocks add overhead. SPI ISR typically advances through two completion phases per slot, implying roughly 45,000 entries/s if every nominal bank runs. This is a load estimate based on control flow.

Measure DCLK, LE, grayscale clock, one row line, and input latency on a separately authorized bench pass. Correlate frame transactions with bank-zero rollover. Leave TIMER1, SPI0, PWM0, GPIO mux/row switching, blanking, USB IRQ, keyboard scan and software timer paths enabled in external mode.
