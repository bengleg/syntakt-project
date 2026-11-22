/* delay-control: Octatrack-style freeze / beat repeat on trig modifier MOD B (Syntakt OS 1.41).
 *
 * Active while the OS's selected trig modifier is MOD B (FUNC + TRIG 16):
 * - the stock delay is silenced: its input bus is zeroed before it runs and its output after;
 * - a rolling 1-beat buffer records the FX bus (digital tracks routed to the analog FX block);
 * - holding TRIG 13-16 freezes it: the FX bus is replaced by a loop of the latest N samples
 *   (N = the slot's divider), which also mutes those tracks' dry sound. A shorter slot pressed while
 *   frozen chops the loop to its latest part and locks it; a longer one keeps the locked length.
 *   Releasing every key returns the dry sound at once and recording resumes.
 *
 * Hooks:
 * - keys 13-16 of KeyboardView::consumeKeyEvent (0x4002EA92), as beat-repeat: consumed while active;
 * - event dispatcher (0x4000B420): releases anywhere, and the active flag after each event;
 * - delay call (0x4008F828) and the mix function after the FX bus sums (0x4008FB04), as fx3.
 * Audio blocks: 32 frames, 48 kHz, buses of 32 x {L, R} s32.
 */

typedef unsigned int u32;
typedef int s32;

#define DATA __attribute__((section(".data")))

/* Digital tracks routed to the analog FX block. The SyntHack notes name 0x8000DFD0 for this, but on the
 * device freezing 0x8000DFD0 froze the tracks NOT routed to the FX block: the two buses are swapped. */
#define FX_BUS   ((s32 *)0x8000DAD0u)                  /* L/R interleaved, 32 frames */
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

const char *volatile dc_view DATA = 0;                 /* KeyboardView, seen at consumeKeyEvent entry */
#ifdef DC_DEBUG
#define POPUP ((void (*)(void *, const char *, ...))0x400C33D0u)
static s32 dc_dbg_sel DATA = -99;
#endif

static void update_active(void)
{
    u32 project, a;
    if (!dc_view)
        return;
    project = *(const u32 *)(dc_view + VIEW_PROJECT);
    if (!project)
        return;
    {
        s32 sel = GET_SEL(STORE(PAT_ENTRY(project)));
#ifdef DC_DEBUG
        if (sel != dc_dbg_sel) {
            dc_dbg_sel = sel;
            POPUP(*(void *const *)(dc_view + 152), "DC sel %d P%08x", sel, project);
        }
#endif
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

#ifdef SNAP_PROBE
void dc_snap_show(const char *view);
#endif

/* keys 13-16 after the OS mode checks: 1 = consumed, -1 = stock behavior */
s32 dc_kbd(const char *view, const unsigned char *ev, u32 code)
{
    dc_view = view;
    if (code < KEY_13 || code > KEY_13 + 3)
        return -1;
    update_active();
#ifdef SNAP_PROBE
    dc_snap_show(view);
#endif
#ifdef DC_DEBUG
    POPUP(*(void *const *)(view + 152), "A%02x%02x%02x%02x M%x",
          dc_pk[0] >> 23, dc_pk[1] >> 23, dc_pk[2] >> 23, dc_pk[3] >> 23, dc_amute >> 8);
    dc_pk[0] = dc_pk[1] = dc_pk[2] = dc_pk[3] = dc_pk[4] = 0;
#endif
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

/* Full-wave rectifier ahead of the analog FX Drive, on the same bus (digital tracks routed to the FX block).
 * DRIVE (FX track, engine copy 0x800028F0, 0..0x7F00, shown 0..11): stock below 5, then a linear blend from
 * clean at 5 to fully rectified (|x|) at 11. No DC removal (by request). */
#define DRIVE    (*(const volatile unsigned short *)0x800028F0u)
#define DRV_LO   (0x7F00u * 5 / 11)                    /* display 5 */
#define DRV_HI   0x7F00u                               /* display 11 */

static void rectify(void)
{
    u32 v = DRIVE, i;
    s32 a;
    if (v <= DRV_LO)
        return;
    a = (s32)((v - DRV_LO) * 256u / (DRV_HI - DRV_LO));
    if (a > 256)
        a = 256;
    for (i = 0; i < 2 * FRAMES; i++) {
        s32 x = FX_BUS[i], r = x < 0 ? (x == (s32)0x80000000 ? 0x7FFFFFFF : -x) : x;
        FX_BUS[i] = a == 256 ? r : (x >> 8) * (256 - a) + (r >> 8) * a;
    }
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
u32 dc_pk[5] DATA = {0, 0, 0, 0, 0};                   /* debug: peaks of ADC 0-3 and of the bus */

static u32 analog_routed(void)                         /* bit c: track 9+c routed to the FX block */
{
    u32 c, m = 0;
    for (c = 0; c < 4; c++)
        if (!ROUT(8 + c))                              /* ROUT 0 = through the FX block (found on the device) */
            m |= 1u << c;
    return m;
}

#ifdef DC_DEBUG
static void peaks(void)
{
    u32 c, i;
    for (c = 0; c < 5; c++) {
        const s32 *p = c < 4 ? ADC(c) : FX_BUS;
        u32 n = c < 4 ? FRAMES : 2 * FRAMES, pk = dc_pk[c];
        for (i = 0; i < n; i++) {
            s32 x = p[i];
            u32 a = x < 0 ? (u32)-x : (u32)x;
            if (a > pk)
                pk = a;
        }
        dc_pk[c] = pk;
    }
}
#endif

static void delay_control(void);

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

void dc_run(void)
{
#ifdef DC_DEBUG
    peaks();
#endif
    delay_control();
    rectify();
}

static void delay_control(void)
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

/* DJ filter: FX block filter TYPE 6 (was LP-Notch). Called at the end of the FX filter CV routine
 * (0x40095FA6), with hw = the CV block (a2) and kit = the engine copy base (a3):
 * FREQ 0..63 -> 2-pole lowpass, cutoff stretched so 63 is fully open; 64..127 -> 2-pole highpass from fully
 * open upward. Recomputes the cutoff CVs (hw+74/76, with filter pan, as the OS does) and, on the normal path,
 * the resonance CV (hw+78) with the LP2/HP2 tables. Returns the type to use for the mode bits, or -1. */
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
    if (!dc_view || ACTIVE_TRACK(*(const u32 *)(dc_view + 160)) != 12)
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

#ifdef SNAP_PROBE
/* Probe build only: hook at the start of the OS parameter setter 0x4000DA32 (?, param id, kit object, value).
 * For the FX filter FREQ (id 133) the first four values written since the last show are logged (a gesture is
 * many small writes; a FUNC snap would be in the first ones) and shown as raw hex when TRIG 13-16 is pressed
 * (the OS's own value readout hides popups raised during a turn). */
#define POPUPF    ((void (*)(void *, const char *, ...))0x400C33D0u)
u32 sp_log[4] DATA = {0, 0, 0, 0};
u32 sp_n DATA = 0;

void dc_snap_pre(u32 id, u32 value)
{
    if (id != 133 || sp_n >= 4)
        return;
    sp_log[sp_n++] = value;
}

void dc_snap_show(const char *view)
{
    POPUPF(*(void *const *)(view + 152), "%08x %08x %08x %08x", sp_log[0], sp_log[1], sp_log[2], sp_log[3]);
    sp_log[0] = sp_log[1] = sp_log[2] = sp_log[3] = 0;
    sp_n = 0;
}

__asm__(
    "        .globl  dc_snap_hook\n"
    "dc_snap_hook:\n"                           /* 0x4000DA32: entered like the function itself */
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        move.l  32(%sp),-(%sp)\n"          /* value */
    "        move.l  28(%sp),-(%sp)\n"          /* id */
    "        jsr     dc_snap_pre\n"
    "        addq.l  #8,%sp\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        move.l  %d3,-(%sp)\n"              /* replaced instructions */
    "        move.l  %d2,-(%sp)\n"
    "        move.l  12(%sp),%d1\n"
    "        jmp     0x4000DA3A\n");
#endif

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
    "        .globl  dc_syn_stub\n"
    "dc_syn_stub:\n"                            /* 0x40195156, instead of clr.l 0x41B9F968 (FX SYN slot 7): */
    "        move.l  %d0,-(%sp)\n"              /* the OS has just cleared slots 1-6; fill 1-7 (8 = DRIVE) */
    "        move.l  #120,%d0\n"                /* reverb HPF */
    "        move.l  %d0,0x41B9F950\n"
    "        move.l  #121,%d0\n"                /* reverb LPF */
    "        move.l  %d0,0x41B9F954\n"
    "        move.l  #117,%d0\n"                /* reverb DECAY */
    "        move.l  %d0,0x41B9F958\n"
    "        move.l  #152,%d0\n"                /* FX amp reverb send */
    "        move.l  %d0,0x41B9F95C\n"
    "        move.l  #133,%d0\n"                /* FX filter FREQ, RESO, TYPE: as FLTR slots 5-7 */
    "        move.l  %d0,0x41B9F960\n"
    "        move.l  #134,%d0\n"
    "        move.l  %d0,0x41B9F964\n"
    "        move.l  #143,%d0\n"                /* slot 7: FX filter pan (FLTR page 2 slot 5) */
    "        move.l  %d0,0x41B9F968\n"
    "        move.l  (%sp)+,%d0\n"
    "        rts\n"
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
    "        .globl  dc_page_hook\n"
    "dc_page_hook:\n"                           /* 0x40042938, page draw dispatcher: d0 = page number. */
    "        moveq   #32,%d1\n"                 /* FX SYN (page 32) is drawn by the filter-page routine */
    "        cmp.l   %d0,%d1\n"                 /* like pages 7/9/11: FREQ+RESO (slots 5-6) as the curve */
    "        bne.s   1f\n"
    "        moveq   #7,%d0\n"
    "1:      moveq   #7,%d1\n"                  /* replaced: moveq #7,d1 ; cmp.l d0,d1 ; beq.s 0x40042948 */
    "        cmp.l   %d0,%d1\n"
    "        bne.s   2f\n"
    "        addq.l  #4,%sp\n"
    "        jmp     0x40042948\n"
    "2:      rts\n"
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
    "        rts\n"
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
    "        .globl  dc_entry_hook\n"
    "dc_entry_hook:\n"                          /* 0x4002E850, KeyboardView::consumeKeyEvent(this, event) */
    "        move.l  8(%sp),%a0\n"              /* this */
    "        move.l  %a0,dc_view\n"
    "        move.l  (%sp)+,%a0\n"
    "        link.w  %fp,#-84\n"                /* replaced instructions */
    "        movem.l %d2-%d7/%a2-%a5,(%sp)\n"
    "        jmp     (%a0)\n"
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
    "        rts\n"
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
