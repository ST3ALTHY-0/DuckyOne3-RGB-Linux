.syntax unified
.cpu cortex-m0
.thumb

.section .text,"ax",%progbits
.global rgb_dispatcher
.thumb_func

rgb_dispatcher:
    push {r4,r5,r6,lr}

    ldr r4, =0x2000254c

    @ Validate custom HID command header
    ldrb r0, [r4,#0]
    cmp r0, #0
    bne forward

    ldrb r0, [r4,#1]
    cmp r0, #0x3a
    bne forward

    ldrb r0, [r4,#2]
    cmp r0, #0
    bne forward

    ldrb r0, [r4,#3]
    cmp r0, #0
    bne forward

    ldrb r0, [r4,#4]
    cmp r0, #1
    bne forward

    ldrb r0, [r4,#5]
    cmp r0, #2
    bne forward

    @ Validate bank and index
    ldrb r0, [r4,#6]
    cmp r0, #5
    bhs done

    ldrb r5, [r4,#7]
    cmp r5, #15
    bhs done

    lsls r0, r0, #8
    orrs r0, r5

    @ Preserve original LED ID
    mov r6, r0

    @ Validate remapped LED coordinates
    movs r0, #1
    mov r1, r6

    ldr r5, =0x00004BE3
    blx r5

    @ map_logical_key() returns mapped ID in r0
    lsrs r1, r0, #8
    cmp r1, #5
    bhs done

    movs r1, #0xff
    ands r0, r1
    cmp r0, #15
    bhs done

    @ Restore original LED ID
    mov r0, r6

    @ Convert 8-bit RGB to 16-bit
    ldrb r1, [r4,#8]
    lsls r5, r1, #8
    adds r1, r1, r5

    ldrb r2, [r4,#9]
    lsls r5, r2, #8
    adds r2, r2, r5

    ldrb r3, [r4,#10]
    lsls r5, r3, #8
    adds r3, r3, r5

    @ Call original RGB writer
    ldr r5, =0x00003161
    blx r5

    @ Request lighting update
    ldr r5, =0x200027b0
    movs r0, #1
    strb r0, [r5]

    b done

forward:
    @ Preserve original HID processing
    ldr r5, =0x00009655
    blx r5

done:
    pop {r4,r5,r6,pc}

    .align 2
