# LED mapping

A logical LED ID encodes the bank in its high byte and the index in its low byte. For example, bank 1, index 4 is `0x0104`.

The dispatcher checks the input bank and index and calls the firmware remapper. It checks that the mapped bank is below 5 and the mapped index is below 15 before passing the original logical ID to the RGB writer. Each 8-bit color channel is multiplied by 257 to fill the 16-bit range.

The original firmware's startup data contains four pairs of little-endian 16-bit LED IDs. The keyboard layout and firmware mapping determine which physical key corresponds to each ID.
