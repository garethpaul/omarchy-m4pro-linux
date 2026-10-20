.text
.global _start
_start:
    bl smptest
    brk #0
