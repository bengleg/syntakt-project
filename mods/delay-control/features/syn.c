/* FX SYN page: reverb / send / filter / Drive shortcuts. One hook (0x40195156), no state, no dependencies. */

#include "dc.h"

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
    "        rts\n");
