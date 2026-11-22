/* dc-diag: diagnostic for Delay Control (Syntakt OS 1.41). Changes no behavior.
 *
 * - Event dispatcher (0x4000B420): every key event updates a held-key mask (codes 0..63).
 * - Keys 13-16 branch of KeyboardView::consumeKeyEvent (0x4002EA92): pops up
 *   "K<code> D<down> H<mask hi>.<mask lo>" with the OS popup (view+152), then the OS continues as stock.
 * - Once the popup manager is known, presses of codes 36-39 seen by the dispatcher pop up too, as "E...".
 *   If FUNC+16 shows "E39" but never "K39", FUNC combos do not reach the 13-16 branch.
 */

typedef unsigned int u32;
typedef int s32;

#define DATA __attribute__((section(".data")))
#define POPUP ((void (*)(void *, const char *, ...))0x400C33D0u)
#define EV_DOWN 1u

u32 dg_held[2] DATA = {0, 0};
void *dg_mgr DATA = 0;
static u32 dg_in_kbd DATA = 0;

void dg_ev(void *root, const unsigned char *ev)
{
    u32 code = *(const u32 *)(ev + 12), fl = *(const u32 *)(ev + 16);
    (void)root;
    if (code < 64) {
        u32 bit = 1u << (code & 31);
        if (fl & EV_DOWN)
            dg_held[code >> 5] |= bit;
        else
            dg_held[code >> 5] &= ~bit;
    }
    if ((fl & EV_DOWN) && code >= 36 && code <= 39 && dg_mgr && !dg_in_kbd)
        POPUP(dg_mgr, "E%d H%08x.%08x", (s32)code, dg_held[1], dg_held[0]);
}

void dg_kbd(const char *view, const unsigned char *ev, u32 code)
{
    u32 fl = *(const u32 *)(ev + 16);
    dg_mgr = *(void *const *)(view + 152);
    if (code < 36 || code > 39)
        return;
    dg_in_kbd = 1;
    POPUP(dg_mgr, "K%d D%d H%08x.%08x", (s32)code, (s32)(fl & EV_DOWN), dg_held[1], dg_held[0]);
    dg_in_kbd = 0;
}

__asm__(
    "        .globl  dg_kbd_hook\n"
    "dg_kbd_hook:\n"                            /* 0x4002EA92: d0 = code, d2 = event, a2 = view */
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        move.l  %d0,-(%sp)\n"
    "        move.l  %d2,-(%sp)\n"
    "        move.l  %a2,-(%sp)\n"
    "        jsr     dg_kbd\n"
    "        lea     12(%sp),%sp\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        moveq   #35,%d1\n"                 /* replaced instructions */
    "        cmp.l   %d0,%d1\n"
    "        bge.s   2f\n"
    "        jmp     0x4002EA9A\n"
    "2:      jmp     0x4002EBA6\n"
    "        .globl  dg_ev_hook\n"
    "dg_ev_hook:\n"                             /* instead of jsr 0x4000839E (dispatcher) */
    "        lea     -16(%sp),%sp\n"
    "        movem.l %d0-%d1/%a0-%a1,(%sp)\n"
    "        move.l  24(%sp),-(%sp)\n"
    "        move.l  24(%sp),-(%sp)\n"
    "        jsr     dg_ev\n"
    "        addq.l  #8,%sp\n"
    "        movem.l (%sp),%d0-%d1/%a0-%a1\n"
    "        lea     16(%sp),%sp\n"
    "        jmp     0x4000839E\n");
