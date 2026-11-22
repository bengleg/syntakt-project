/* DJ filter: FX block filter TYPE 6 (was LP-Notch). Called at the end of the FX filter CV routine
 * (0x40095FA6), with hw = the CV block (a2) and kit = the engine copy base (a3):
 * FREQ 0..63 -> 2-pole lowpass, cutoff stretched so 63 is fully open; 64..127 -> 2-pole highpass from fully
 * open upward. Recomputes the cutoff CVs (hw+74/76, with filter pan, as the OS does) and, on the normal path,
 * the resonance CV (hw+78) with the LP2/HP2 tables. Returns the type to use for the mode bits, or -1.
 * Hooks: CV routine, type name, type icon, filter-tab curve. The curve needs DC_VIEW (the runtime's entry hook).
 */

#include "dc.h"

#define K_TYPE   1820
#define K_FREQ   1822
#define K_RESO   1824
#define K_FPAN   1840
#define T_LP2    1
#define T_HP2    3
#define T_DJ     6
#define FLT_MODE (*(const volatile unsigned char *)0x43BDC044u)
#define RESO_LP2 ((const short *)0x40249D18u)
#define RESO_HP2 ((const short *)0x40249B18u)
#define RESO_FRQ ((const short *)0x40249A18u)

static s32 clamp_cv(s32 v)
{
    if (v < 0)
        v = 0;
    else if (v > 65024)
        v = 65024;
    return v - 32768;
}

/* DJ zones on FREQ (0..0x7F00): LP below DJ_LO (fully open at DJ_LO), filter OFF (bypass) in between,
 * HP from DJ_HI (fully open there). The cutoff jumps from top to bottom in the middle of the bypass zone,
 * where it can't be heard, instead of together with the LP -> HP mode switch (that was the pop). */
#define T_OFF    7
#define DJ_LO    0x3E00u                               /* display 62 */
#define DJ_HI    0x4200u                               /* display 66 */

/* The bypass zone (v2g) is kept for a later try; disabled: back to the v2f mapping (pop accepted for now). */
#define DJ_BYPASS 0

static s32 dj_zone(u32 f, u32 *fp)                     /* type for FREQ f; *fp = cutoff 0..0x7F00 */
{
    if (!DJ_BYPASS) {                                  /* v2f: LP 0..63 fully open at 63, HP from 64 */
        u32 x = f < 0x4000 ? f : f - 0x4000;
        if (x > 0x3F00)
            x = 0x3F00;
        *fp = x * 0x7F00u / 0x3F00u;
        return f < 0x4000 ? T_LP2 : T_HP2;
    }
    if (f < DJ_LO) {
        *fp = f * 0x7F00u / DJ_LO;
        return T_LP2;
    }
    if (f >= DJ_HI) {
        u32 x = f > 0x7F00 ? 0x7F00 : f;
        *fp = (x - DJ_HI) * 0x7F00u / (0x7F00u - DJ_HI);
        return T_HP2;
    }
    *fp = f < 0x4000 ? 0x7F00 : 0;
    return T_OFF;
}

s32 dc_flt(char *hw, const char *kit)
{
    u32 fp;
    s32 pan, c, t;
    if (kit[K_TYPE] != T_DJ)
        return -1;
    t = dj_zone(*(const unsigned short *)(kit + K_FREQ), &fp);
    pan = 2 * ((s32)*(const short *)(kit + K_FPAN) - 16384);
    c = 2 * (s32)fp;
    *(short *)(hw + 74) = (short)clamp_cv(c - pan);
    *(short *)(hw + 76) = (short)clamp_cv(c + pan);
    if ((FLT_MODE & 31) > 1) {
        s32 r = *(const short *)(kit + K_RESO) >> 8;
        if (t == T_OFF)
            *(short *)(hw + 78) = -20000;              /* as the OS for type OFF */
        else
            *(short *)(hw + 78) = (short)((t == T_LP2 ? RESO_LP2 : RESO_HP2)[r]
                                          - RESO_FRQ[(signed char)(fp >> 8)]);
    }
    return t;
}

const char dc_s_dj[] = "DJ";                           /* TYPE 6 name (was "LPN") */

/* FLTR page curve (filter tab draw, 0x40042646): p[0] = type index (d6), p[1] = FREQ (a4). On the FX track,
 * DJ is drawn as the LP2 / HP2 curve with the cutoff where the DJ filter puts it. Analog tracks share this
 * drawing code and keep their real type 6 (LP-Notch). */
#define ACTIVE_TRACK ((u32 (*)(u32))0x4001FF74u)

void dc_fdraw(u32 *p)
{
    u32 fp;
    s32 t;
    if (!DC_VIEW || ACTIVE_TRACK(*(const u32 *)(DC_VIEW + 160)) != 12)
        return;
    /* the FX SYN page has no TYPE slot (d6 stays 0): always take the FX filter's real type from the engine */
    p[0] = (u32)(*(const volatile signed char *)0x800028CCu & 7);
    if (p[0] != T_DJ)
        return;
    t = dj_zone(p[1], &fp);
    p[0] = (u32)t;
    if (t != T_OFF)
        p[1] = fp;
}

/* TYPE slot icon (FX filter TYPE, id 135, graphic invoker 0x40070B10): type 6 draws the text "DJ" instead of
 * the LP-Notch icon; dc_tgfx (asm) forwards every other type to the stock icon. Only id 135 uses this, so
 * the analog tracks' filter TYPE keeps its icons. Text drawing as beat-repeat's slot text. */
#define DRAW_TEXT ((void (*)(void *, const void *, s32, s32, s32, s32, const char *, const char *, ...)) \
                   0x400F8C18u)
#define FONT      ((const void *)0x402A91C0u)

void dc_tgfx_dj(void *ctx, s32 x, s32 y)
{
    DRAW_TEXT(ctx, FONT, x + 8, y + 5, 1, 0, "XXXX", "%s", dc_s_dj);
}

__asm__(
    "        .globl  dc_flt_hook\n"
    "dc_flt_hook:\n"                            /* 0x40095FA6: instead of move.b 164(a2),d0 ; moveq #-8,d1 */
    "        lea     -16(%sp),%sp\n"            /* d2 = filter type for the mode bits, a2 = CV block, */
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"   /* a3 = engine copy */
    "        move.l  %a3,-(%sp)\n"
    "        move.l  %a2,-(%sp)\n"
    "        jsr     dc_flt\n"
    "        addq.l  #8,%sp\n"
    "        tst.l   %d0\n"
    "        bmi.s   1f\n"
    "        move.l  %d0,%d2\n"
    "1:      movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        move.b  164(%a2),%d0\n"            /* replaced instructions */
    "        moveq   #-8,%d1\n"
    "        rts\n"
    "        .globl  dc_fdraw_hook\n"
    "dc_fdraw_hook:\n"                          /* 0x40042646: instead of lea 0x40039160,a3 */
    "        lea     -16(%sp),%sp\n"            /* d6 = filter type, a4 = FREQ, for the curve */
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        move.l  %a4,-(%sp)\n"
    "        move.l  %d6,-(%sp)\n"
    "        pea     (%sp)\n"
    "        jsr     dc_fdraw\n"
    "        addq.l  #4,%sp\n"
    "        move.l  (%sp)+,%d6\n"
    "        move.l  (%sp)+,%a4\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        lea     0x40039160,%a3\n"          /* replaced instruction */
    "        rts\n"
    "        .globl  dc_tgfx\n"
    "dc_tgfx:\n"                                /* TYPE graphic invoker: (fn, value, ctx, x, y) */
    "        move.l  8(%sp),%d0\n"
    "        asr.l   #8,%d0\n"
    "        moveq   #6,%d1\n"
    "        cmp.l   %d0,%d1\n"
    "        beq.s   1f\n"
    "        jmp     0x40070B10\n"              /* stock icon, arguments untouched */
    "1:      move.l  20(%sp),-(%sp)\n"          /* y */
    "        move.l  20(%sp),-(%sp)\n"          /* x */
    "        move.l  20(%sp),-(%sp)\n"          /* ctx */
    "        jsr     dc_tgfx_dj\n"
    "        lea     12(%sp),%sp\n"
    "        rts\n");
