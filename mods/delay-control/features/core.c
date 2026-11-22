/* Freeze / DelayCtrl core: Octatrack-style freeze / beat repeat on trig modifier MOD B (Syntakt OS 1.41).
 *
 * Active while the OS's selected trig modifier is MOD B (FUNC + TRIG 16):
 * - the stock delay is silenced: its input bus is zeroed before it runs and its output after;
 * - a rolling 1-beat buffer records the FX bus (digital tracks routed to the analog FX block);
 * - holding TRIG 13-16 freezes it: the FX bus is replaced by a loop of the latest N samples
 *   (N = the slot's divider), which also mutes those tracks' dry sound. A shorter slot pressed while
 *   frozen chops the loop to its latest part and locks it; a longer one keeps the locked length.
 *   Releasing every key returns the dry sound at once and recording resumes.
 *
 * Hooks: keys 13-16 of KeyboardView::consumeKeyEvent (0x4002EA92), the event dispatcher (0x4000B420), the delay
 * call (0x4008F828), the external-in and analog voice CV routines, the RETRIG-style DCTL setup page (MOD B
 * M1-M4) and the MOD B names. The mix hook (0x4008FB04) is shared: the runtime (common.c) calls dc_core_run
 * through DC_REG_CORE. Audio blocks: 32 frames, 48 kHz, buses of 32 x {L, R} s32.
 */

#include "dc.h"

#define DLY_IN   ((s32 *)0x8000DBD0u)
#define DLY_OUT  ((s32 *)0x8000DCD0u)
#define TEMPO    (*(const volatile u32 *)0x402D7010u)  /* BPM x 120 */
#define FRAMES   32
#define RING_LOG 17
#define RING     (1u << RING_LOG)                      /* frames: 1 beat down to ~22 BPM */
#define RING_BUF ((s32 *)0x46100000u)                  /* RAM unused by the OS, 1 MB */
#define XF       256                                   /* loop-point crossfade, frames (max, <= loop/4) */
#define EF       128                                   /* fade at freeze start and release, frames */

#define KEY_13   36
#define EV_DOWN  1u
#define MOD_B    3

/* selected trig modifier, as the OS's FUNC+13-16 handler (0x40040AFE) reaches it:
 * entry = 0x40019000(project) = project + 13204 + 1664 * pattern, store = entry + 44 (0x40016056),
 * selection = 0x40015AF6(store). The project is *(KeyboardView + 148), as in consumeKeyEvent. */
/* The OS returns pointers in d0 (this gcc would expect a0): declare them as returning u32. */
#define PAT_ENTRY ((u32 (*)(u32))0x40019000u)
#define STORE    ((u32 (*)(u32))0x40016056u)
#define GET_SEL  ((s32 (*)(u32))0x40015AF6u)
#define VIEW_PROJECT 148
/* parameter store of the project (as 0x4002D762 reads the RETRIG values): store = 0x400186E8(project),
 * value = store->vtbl[40](store, id) */
#define PARAM_STORE ((u32 (*)(u32))0x400186E8u)

/* shared between UI (keys) and the audio interrupt: single aligned words */
volatile u32 dc_active DATA = 0;
volatile u32 dc_held DATA = 0;                         /* bit i: TRIG 13+i held */
volatile u32 dc_order[4] DATA = {0, 0, 0, 0};          /* press stamps, 0 = not held */
static u32 dc_count DATA = 0;
/* Per-slot rate: the loop is 1/N of a bar (N from the RETRIG rate list), read from MOD B's M1-M4 (ids 54-57)
 * on every key event. Defaults 1/4, 1/8, 1/16, 1/32. N < 4 is capped at one beat (the buffer). */
volatile unsigned char dc_rate[4] DATA = {4, 8, 16, 32};
static const unsigned char rate_n[17] = {1, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 24, 32, 40, 48, 64, 80};
/* The DCTL boxes offer 9 steps (values 0..0x800): RETRIG list entries 1/4, 1/6, 1/8, 1/12, 1/16, 1/24, 1/32,
 * 1/48, 1/64. Used by the box wrappers (to show the right RETRIG text) and by the slot rates. */
#define N_STEPS 9
const unsigned char dc_allowed[N_STEPS] = {3, 5, 6, 8, 9, 11, 12, 14, 15};

/* audio state */
u32 dc_wpos DATA = 0;                                  /* next write frame */
u32 dc_written DATA = 0;                               /* valid frames in the ring (capped) */
u32 dc_frozen DATA = 0;
u32 dc_end DATA = 0;                                   /* freeze point (frame after the last one) */
u32 dc_lock DATA = 0;                                  /* loop length, frames */
u32 dc_pos DATA = 0;                                   /* play position inside the loop */
u32 dc_hist DATA = 0;                                  /* frames available before the loop start */
u32 dc_fin DATA = 0;                                   /* frames faded in since the freeze */
u32 dc_fout DATA = 0;                                  /* release fade frames left */

static void update_active(void)
{
    u32 project, a;
    if (!DC_VIEW)
        return;
    project = *(const u32 *)(DC_VIEW + VIEW_PROJECT);
    if (!project)
        return;
    {
        s32 sel = GET_SEL(STORE(PAT_ENTRY(project)));
        a = sel == MOD_B;
    }
    if (a) {                                           /* slot rates from MOD B M1-M4 (ids 54-57) */
        u32 store = PARAM_STORE(project), c;
        u32 get = *(const u32 *)(*(const u32 *)store + 40);
        for (c = 0; c < 4; c++) {
            s32 i = ((s32 (*)(u32, u32))get)(store, 54 + c) >> 8;
            if (i < 0)
                i = 0;
            if (i > N_STEPS - 1)
                i = N_STEPS - 1;
            dc_rate[c] = rate_n[dc_allowed[i]];
        }
    }
    if (!a && dc_active) {
        dc_held = 0;
        dc_count = 0;
    }
    dc_active = a;
}

static void key(u32 i, u32 down)
{
    if (down) {
        dc_order[i] = ++dc_count;
        dc_held |= 1u << i;
    } else {
        dc_held &= ~(1u << i);
        dc_order[i] = 0;
        if (!dc_held)
            dc_count = 0;
    }
}

/* keys 13-16 after the OS mode checks: 1 = consumed, -1 = stock behavior */
s32 dc_kbd(const char *view, const unsigned char *ev, u32 code)
{
    DC_VIEW = view;
    if (code < KEY_13 || code > KEY_13 + 3)
        return -1;
    update_active();
    if (!dc_active)
        return -1;
    key(code - KEY_13, *(const u32 *)(ev + 16) & EV_DOWN);
    return 1;
}

/* every key event, before dispatch: catch releases wherever they land */
void dc_ev(void *root, const unsigned char *ev)
{
    u32 code = *(const u32 *)(ev + 12), fl = *(const u32 *)(ev + 16);
    (void)root;
    if (!(fl & EV_DOWN) && code >= KEY_13 && code <= KEY_13 + 3 && (dc_held & (1u << (code - KEY_13))))
        key(code - KEY_13, 0);
}

/* after dispatch: the selection may have changed (FUNC + TRIG 13-16) */
void dc_post(void)
{
    update_active();
}

static u32 slot_len(u32 slot)                          /* divider of the slot, in frames */
{
    u32 t = TEMPO, q;
    if (t < 120 * 20)
        t = 120 * 20;
    q = 345600000u / t;                                /* 48000 * 60 * 120 / (BPM * 120) */
    if (q > RING - FRAMES)
        q = RING - FRAMES;
    {
        u32 n = dc_rate[slot];                         /* 1/N bar = 4/N beat */
        if (n < 4)
            n = 4;
        return q * 4u / n;
    }
}

static u32 last_slot(void)
{
    u32 i, best = 0, s = 0;
    for (i = 0; i < 4; i++)
        if (dc_order[i] > best) {
            best = dc_order[i];
            s = i;
        }
    return s;
}

static void zero(s32 *p)
{
    u32 i;
    for (i = 0; i < 2 * FRAMES; i++)
        p[i] = 0;
}

void dc_del_pre(void)
{
    if (dc_active)
        zero(DLY_IN);
}

void dc_del_post(void)
{
    if (dc_active)
        zero(DLY_OUT);
}

static s32 *frame(u32 f)
{
    return RING_BUF + 2 * (f & (RING - 1));
}

/* Analog tracks 9-12 (t = 8..11): each voice is digitized into ADC channel t-8 (0x80003950 + 128*c, 32 s32,
 * mono). Routing to the FX block = track ROUT (id 82, internal 0x31): engine word 0x800021B0 + 142*t + 126.
 * Muting: the per-block CV loop (0x400903F4) reads the mute mask 0x80003150 (bit = track) for the 4 voices;
 * dc_mute_hook ORs dc_amute into it. */
#define ADC(c)    ((const s32 *)(0x80003950u + 128u * (c)))
#define ROUT(t)   (*(const volatile unsigned short *)(0x800021B0u + 142u * (t) + 126u))
volatile u32 dc_amute DATA = 0;
/* External input: ADC 4 (L) / 5 (R). Routing word 0x800028CA ("In FX Routing", engine a2+1818): 0 = through
 * the FX block (the OS then compensates its level by DRIVE, 0x4009089A). While frozen, its level CVs
 * (hw+8 L, hw+18 R, written just before 0x400908FC) are zeroed by dc_ext_hook. */
#define EXT_ROUT  (*(const volatile unsigned short *)0x800028CAu)
#define EXT_MONO  (*(const volatile unsigned char *)0x80003146u == 0)
volatile u32 dc_emute DATA = 0;
/* Analog CV block, saved by dc_mute_hook (the CV routine's a3): u16 levels, voice c left = cv[c], right =
 * cv[5 + c], external in left = cv[4], right = cv[9] (0..65535, 65535 = unity). Captured analog and
 * external audio is scaled by them, so the loop keeps the track level and pan. 0 = not seen yet (unity). */
const unsigned short *volatile dc_hw DATA = 0;
/* Scaling by the CVs (v2g) made analog tracks far too quiet on the device: the CVs are not linear gains with
 * 65535 = unity. Disabled (v2f behavior: unity, mono for voices, stereo for the external input) until the
 * CV-to-gain law is known. */
#define CV_LEVELS 0

static void add_scaled(u32 c_adc, u32 cv_l, u32 cv_r)  /* ADC channel into the ring, with L/R levels */
{
    const unsigned short *cv = CV_LEVELS ? dc_hw : 0;
    u32 gl = cv ? cv[cv_l] >> 8 : 256, gr = cv ? cv[cv_r] >> 8 : 256, i;
    const s32 *a = ADC(c_adc);
    for (i = 0; i < FRAMES; i++) {
        s32 *d = frame(dc_wpos + i), x = (a[i] >> 8) * 26; /* DAC scale -> bus scale (bus is x10 later) */
        d[0] += (x >> 8) * (s32)gl;
        d[1] += (x >> 8) * (s32)gr;
    }
}

/* External input capture scale: 128/256. Measured on the device: with the analog-track scale (26/256) the frozen
 * loop of the external input was about 40% of the live level; 65 and 75 were still a bit quiet, 128 by ear. */
#define EXT_SCALE 128

static void add_ext(void)                              /* external input: stereo, or L to both in mono */
{
    const unsigned short *cv = CV_LEVELS ? dc_hw : 0;
    u32 gl = cv ? cv[4] >> 8 : 256, gr = cv ? cv[9] >> 8 : 256, i, mono = CV_LEVELS && EXT_MONO;
    for (i = 0; i < FRAMES; i++) {
        s32 *d = frame(dc_wpos + i), l = (ADC(4)[i] >> 8) * EXT_SCALE, r = mono ? l : (ADC(5)[i] >> 8) * EXT_SCALE;
        d[0] += (l >> 8) * (s32)gl;
        d[1] += (r >> 8) * (s32)gr;
    }
}

static u32 analog_routed(void)                         /* bit c: track 9+c routed to the FX block */
{
    u32 c, m = 0;
    for (c = 0; c < 4; c++)
        if (!ROUT(8 + c))                              /* ROUT 0 = through the FX block (found on the device) */
            m |= 1u << c;
    return m;
}

/* next frame of the loop (with the loop-point crossfade), advancing the play position */
static void loop_frame(s32 *pl, s32 *pr)
{
    u32 start = dc_end - dc_lock, xf = XF;
    const s32 *s = frame(start + dc_pos);
    s32 l = s[0], r = s[1];
    if (xf > dc_lock / 4)
        xf = dc_lock / 4;
    if (xf > dc_hist)
        xf = dc_hist;
    if (xf && dc_pos >= dc_lock - xf) {                /* fade into the audio just before the start */
        const s32 *p = frame(start + dc_pos - dc_lock);
        s32 a = (s32)((dc_pos - (dc_lock - xf)) * 256u / xf);
        l = (l >> 8) * (256 - a) + (p[0] >> 8) * a;
        r = (r >> 8) * (256 - a) + (p[1] >> 8) * a;
    }
    if (++dc_pos >= dc_lock)
        dc_pos = 0;
    *pl = l;
    *pr = r;
}

/* the mix hook, through the shared runtime: freeze / beat repeat for this audio block */
void dc_core_run(void)
{
    u32 i, held = dc_held;

    if (!dc_active) {
        dc_frozen = 0;
        dc_fout = 0;
        dc_written = 0;
        dc_amute = 0;
        dc_emute = 0;
        return;
    }
    if (!held) {
        u32 an = analog_routed(), c;
        if (dc_frozen) {                               /* release: fade the loop out over EF frames */
            dc_frozen = 0;
            dc_fout = dc_lock ? EF : 0;
        }
        dc_amute = 0;
        dc_emute = 0;
        for (i = 0; i < FRAMES; i++) {
            s32 *d = frame(dc_wpos + i);
            d[0] = FX_BUS[2 * i];
            d[1] = FX_BUS[2 * i + 1];
        }
        if (!EXT_ROUT)                                 /* external input through the FX block */
            add_ext();
        for (c = 0; an; c++, an >>= 1)                 /* analog tracks routed to the FX block */
            if (an & 1)
                add_scaled(c, c, 5 + c);               /* with the voice's own left / right levels */
        dc_wpos = (dc_wpos + FRAMES) & (RING - 1);
        if (dc_written < RING)
            dc_written += FRAMES;
        for (i = 0; i < FRAMES && dc_fout; i++, dc_fout--) {
            s32 l, r, a = (s32)(dc_fout * 256u / EF);  /* loop weight, 256 -> 0 */
            loop_frame(&l, &r);
            FX_BUS[2 * i] = (l >> 8) * a + (FX_BUS[2 * i] >> 8) * (256 - a);
            FX_BUS[2 * i + 1] = (r >> 8) * a + (FX_BUS[2 * i + 1] >> 8) * (256 - a);
        }
        return;
    }
    {
        u32 want = slot_len(last_slot());
        if (!dc_frozen) {
            dc_frozen = 1;
            dc_fin = 0;
            dc_fout = 0;
            dc_end = dc_wpos;
            dc_lock = want < dc_written ? want : dc_written;
            dc_pos = 0;
        } else if (want < dc_lock) {
            dc_lock = want;                            /* chop to the latest part, lock it */
            dc_pos = 0;
        }
        dc_hist = dc_written - dc_lock;
        dc_amute = analog_routed() << 8;               /* mute the routed analog voices (bits = track 8..11) */
        dc_emute = !EXT_ROUT;                          /* and the external input if routed */
    }
    if (!dc_lock) {
        zero(FX_BUS);
        return;
    }
    for (i = 0; i < FRAMES; i++) {
        s32 l, r;
        loop_frame(&l, &r);
        if (dc_fin < EF) {                             /* freeze start: fade live -> loop over EF frames */
            s32 a = (s32)(dc_fin++ * 256u / EF);
            l = (l >> 8) * a + (FX_BUS[2 * i] >> 8) * (256 - a);
            r = (r >> 8) * a + (FX_BUS[2 * i + 1] >> 8) * (256 - a);
        }
        FX_BUS[2 * i] = l;
        FX_BUS[2 * i + 1] = r;
    }
}

/* DCTL setup page: MOD B M1-M4 (ids 54-57) use the RETRIG modifier's text formatter (proto 0x41B9DF00) and
 * slot graphic (proto 0x41B9D930), the boxed "1/16" look, through these prototypes. Their invokers clamp the
 * value to RETRIG's range (0..0x1000: old saved MOD B values go up to 0x7F00 and would read past the 17-entry
 * rate list), then call RETRIG's own invoker with RETRIG's prototype as the function object. */
int dc_mgr(void *dst, const void *src, int op)
{
    (void)dst;
    (void)src;
    (void)op;
    return 0;
}

void dc_mfmt(void);
void dc_mgfx(void);
const void *const dc_mfmt_proto[4] __attribute__((aligned(4))) = {0, 0, (const void *)dc_mgr, (const void *)dc_mfmt};
const void *const dc_mgfx_proto[4] __attribute__((aligned(4))) = {0, 0, (const void *)dc_mgr, (const void *)dc_mgfx};

__asm__(
    "        .globl  dc_mfmt\n"
    "dc_mfmt:\n"                                /* (fn, value, ...): formatter */
    "        lea     0x41B9DF00,%a0\n"
    "        bra.s   1f\n"
    "        .globl  dc_mgfx\n"
    "dc_mgfx:\n"                                /* (fn, value, ctx, x, y): slot graphic */
    "        lea     0x41B9D930,%a0\n"
    "1:      move.l  8(%sp),%d0\n"              /* step = clamp(value >> 8, 0, 8) */
    "        asr.l   #8,%d0\n"
    "        bpl.s   2f\n"
    "        moveq   #0,%d0\n"
    "2:      moveq   #8,%d1\n"
    "        cmp.l   %d1,%d0\n"
    "        ble.s   3f\n"
    "        move.l  %d1,%d0\n"
    "3:      lea     dc_allowed,%a1\n"          /* -> RETRIG list entry, as a RETRIG value */
    "        mvz.b   (0,%a1,%d0.l),%d0\n"
    "        lsl.l   #8,%d0\n"
    "        move.l  %d0,8(%sp)\n"
    "        move.l  %a0,4(%sp)\n"              /* function object = RETRIG's prototype */
    "        move.l  12(%a0),%a0\n"             /* its invoker */
    "        jmp     (%a0)\n");

/* names shown by the OS for MOD B, pointed here by the patch */
const char dc_s_on[] = "DelayCtrl ON";                 /* FUNC + TRIG 16 popup (was "Mod B ON") */
const char dc_s_long[] = "DelayCtrl";                  /* was "Mod B" */
const char dc_s_short[] = "DCTL";                      /* was "MODB" */

__asm__(
    "        .globl  dc_ext_hook\n"
    "dc_ext_hook:\n"                            /* 0x400908FC: instead of move.l #32639,d1 (a3 = CV block) */
    "        tst.l   dc_emute\n"
    "        beq.s   1f\n"
    "        clr.w   8(%a3)\n"                  /* external in L / R level CVs */
    "        clr.w   18(%a3)\n"
    "1:      move.l  #32639,%d1\n"              /* replaced instruction */
    "        rts\n"
    "        .globl  dc_mute_hook\n"
    "dc_mute_hook:\n"                           /* 0x400903F8: instead of mvs.w 0x80003150,d1 (mute mask) */
    "        move.l  %a3,dc_hw\n"               /* the CV block of this block (voice / ext-in levels) */
    "        mvs.w   0x80003150,%d1\n"
    "        or.l    dc_amute,%d1\n"
    "        rts\n"
    "        .globl  dc_kbd_hook\n"
    "dc_kbd_hook:\n"                            /* 0x4002EA92: d0 = code, d2 = event, a2 = view */
    "        move.l  %d0,-(%sp)\n"
    "        move.l  %d0,-(%sp)\n"
    "        move.l  %d2,-(%sp)\n"
    "        move.l  %a2,-(%sp)\n"
    "        jsr     dc_kbd\n"
    "        lea     12(%sp),%sp\n"
    "        tst.l   %d0\n"
    "        bmi.s   1f\n"
    "        addq.l  #4,%sp\n"
    "        jmp     0x4002E954\n"              /* consumed: d3 = 1, exit */
    "1:      move.l  (%sp)+,%d0\n"
    "        moveq   #35,%d1\n"                 /* replaced instructions */
    "        cmp.l   %d0,%d1\n"
    "        bge.s   2f\n"
    "        jmp     0x4002EA9A\n"
    "2:      jmp     0x4002EBA6\n"
    "        .globl  dc_ev_hook\n"
    "dc_ev_hook:\n"                             /* instead of jsr 0x4000839E: (root, event) */
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        move.l  24(%sp),-(%sp)\n"
    "        move.l  24(%sp),-(%sp)\n"
    "        jsr     dc_ev\n"
    "        addq.l  #8,%sp\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        move.l  8(%sp),-(%sp)\n"           /* call the dispatcher with copies of the arguments */
    "        move.l  8(%sp),-(%sp)\n"
    "        jsr     0x4000839E\n"
    "        addq.l  #8,%sp\n"
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        jsr     dc_post\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        rts\n"
    "        .globl  dc_del_hook\n"
    "dc_del_hook:\n"                            /* instead of jsr 0x40096890 (delay) at 0x4008F828 */
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        jsr     dc_del_pre\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        move.l  12(%sp),-(%sp)\n"          /* delay(out 0x8000DCD0, in 0x8000DBD0, params) */
    "        move.l  12(%sp),-(%sp)\n"
    "        move.l  12(%sp),-(%sp)\n"
    "        jsr     0x40096890\n"
    "        lea     12(%sp),%sp\n"
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        jsr     dc_del_post\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        rts\n");
