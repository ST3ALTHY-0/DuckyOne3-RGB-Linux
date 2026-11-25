ENTRY(v4_main_hook)
SECTIONS
{
    . = 0xA7C0;
    .text : { *(.text*) *(.rodata*) }
    .data : { *(.data*) }
    .bss : { *(.bss*) *(COMMON) }
    ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "unexpected allocated RAM")
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.comment*) *(.note*) }
}
