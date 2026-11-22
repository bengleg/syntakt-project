/* DelayCtrl feature packages: shared definitions.
 *
 * Each package is its own translation unit set, linked at its own fixed address in the mod area (see
 * make_features.py, LAYOUT), so a package's bytes never depend on which other packages are selected:
 *   common.c  runtime: the mix-hook dispatcher and the KeyboardView entry hook
 *   core.c    Freeze / DelayCtrl core
 *   dj.c      DJ filter
 *   drive.c   Drive rectifier
 *   syn.c     FX SYN page
 * The mix hook (0x4008FB04) is one hook site that more than one package needs. It calls dc_run, which calls the
 * entry points the selected packages registered in the two words below (zero = not selected, nothing is called).
 * The words and the KeyboardView pointer sit in the first 12 bytes of the mod area. Packages reach them only
 * through these absolute addresses, never through symbols.
 */

#ifndef DC_H
#define DC_H

typedef unsigned int u32;
typedef int s32;

#define DATA __attribute__((section(".data")))

#define DC_REG_CORE  (*(void (*volatile *)(void))0x46004000u)   /* freeze core entry, written by the core package */
#define DC_REG_DRIVE (*(void (*volatile *)(void))0x46004004u)   /* rectifier entry, written by the drive package */
#define DC_VIEW      (*(const char *volatile *)0x46004008u)     /* KeyboardView, stored by the runtime's entry hook */

/* Digital tracks routed to the analog FX block. The SyntHack notes name 0x8000DFD0 for this, but on the
 * device freezing 0x8000DFD0 froze the tracks NOT routed to the FX block: the two buses are swapped. */
#define FX_BUS   ((s32 *)0x8000DAD0u)                  /* L/R interleaved, 32 frames */
#define FRAMES   32

#endif
