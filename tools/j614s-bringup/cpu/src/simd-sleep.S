.text
.global simd_sleep
simd_sleep:
    sub sp, sp, #160
    stp x19, x30, [sp]
    stp q8, q9, [sp, #16]
    stp q10, q11, [sp, #48]
    stp q12, q13, [sp, #80]
    stp q14, q15, [sp, #112]
    mov x19, x0
    str xzr, [sp, #144]
    mov x9, #0x4240
    movk x9, #0xf, lsl #16
    str x9, [sp, #152]
    ldp q0, q1, [x19, #0]
    ldp q2, q3, [x19, #32]
    ldp q4, q5, [x19, #64]
    ldp q6, q7, [x19, #96]
    ldp q8, q9, [x19, #128]
    ldp q10, q11, [x19, #160]
    ldp q12, q13, [x19, #192]
    ldp q14, q15, [x19, #224]
    ldp q16, q17, [x19, #256]
    ldp q18, q19, [x19, #288]
    ldp q20, q21, [x19, #320]
    ldp q22, q23, [x19, #352]
    ldp q24, q25, [x19, #384]
    ldp q26, q27, [x19, #416]
    ldp q28, q29, [x19, #448]
    ldp q30, q31, [x19, #480]
    add x0, sp, #144
    mov x1, xzr
    mov x8, #101
    svc #0
    stp q0, q1, [x19, #0]
    stp q2, q3, [x19, #32]
    stp q4, q5, [x19, #64]
    stp q6, q7, [x19, #96]
    stp q8, q9, [x19, #128]
    stp q10, q11, [x19, #160]
    stp q12, q13, [x19, #192]
    stp q14, q15, [x19, #224]
    stp q16, q17, [x19, #256]
    stp q18, q19, [x19, #288]
    stp q20, q21, [x19, #320]
    stp q22, q23, [x19, #352]
    stp q24, q25, [x19, #384]
    stp q26, q27, [x19, #416]
    stp q28, q29, [x19, #448]
    stp q30, q31, [x19, #480]
    ldp q8, q9, [sp, #16]
    ldp q10, q11, [sp, #48]
    ldp q12, q13, [sp, #80]
    ldp q14, q15, [sp, #112]
    ldp x19, x30, [sp]
    add sp, sp, #160
    ret
