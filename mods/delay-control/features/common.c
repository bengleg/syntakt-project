/* DelayCtrl runtime: the two things more than one package needs. Present whenever a package that uses it is
 * selected. It has no feature behavior of its own: it stores the KeyboardView pointer (DC_VIEW, read by the core
 * and by the DJ filter curve) and, at the mix hook, calls whatever entry points the selected packages registered.
 */

#include "dc.h"

/* Mix hook body (after the FX bus sums): freeze core first, then the rectifier, the order of the single v2o build. */
void dc_run(void)
{
    void (*f)(void) = DC_REG_CORE;
    if (f)
        f();
    f = DC_REG_DRIVE;
    if (f)
        f();
}

__asm__(
    "        .globl  dc_entry_hook\n"
    "dc_entry_hook:\n"                          /* 0x4002E850, KeyboardView::consumeKeyEvent(this, event) */
    "        move.l  8(%sp),%a0\n"              /* this */
    "        move.l  %a0,0x46004008\n"          /* DC_VIEW */
    "        move.l  (%sp)+,%a0\n"
    "        link.w  %fp,#-84\n"                /* replaced instructions */
    "        movem.l %d2-%d7/%a2-%a5,(%sp)\n"
    "        jmp     (%a0)\n"
    "        .globl  dc_mix_hook\n"
    "dc_mix_hook:\n"                            /* 0x4008FB04: instead of pea -296(fp) ; pea 0x8000E0F0 */
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        jsr     dc_run\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        move.l  (%sp)+,%a0\n"
    "        pea     -296(%fp)\n"               /* replaced instructions */
    "        pea     0x8000E0F0\n"
    "        jmp     (%a0)\n");
