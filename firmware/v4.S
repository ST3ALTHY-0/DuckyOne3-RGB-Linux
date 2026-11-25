.syntax unified
.cpu cortex-m0
.thumb

.macro veneer name, body, target
.global \name
.type \name, %function
.thumb_func
\name:
    push {r4,lr}
    bl \body
    pop {r4}
    pop {r3}
    mov lr,r3
    ldr r3, =\target
    bx r3
.size \name, .-\name
.endm

veneer v4_main_hook, v4_supervise, 0x321d
.global v4_reset_hook
.type v4_reset_hook, %function
.thumb_func
v4_reset_hook:
    push {r0,lr}
    bl v4_revoke
    pop {r0,r3}
    mov lr,r3
    ldr r3, =0x8931
    bx r3
.size v4_reset_hook, .-v4_reset_hook
veneer v4_tick_hook, v4_tick, 0x5747
veneer v4_irq_hook, v4_usb_event, 0x9e01

.global v4_compose_hook
.type v4_compose_hook, %function
.thumb_func
v4_compose_hook:
    push {r1,r2,r3,lr}
    add r0, sp, #16
    bl v4_compose
    cmp r0,#0
    pop {r1,r2,r3}
    beq 1f
    add sp,#4
    ldr r0, =0x3f8f
    bx r0
1:
    pop {r0}
    mov lr,r0
    ldr r0, =0x200027a8
    ldrb r0,[r0,#10]
    bx lr
.size v4_compose_hook, .-v4_compose_hook

.ltorg
.section .note.GNU-stack,"",%progbits
