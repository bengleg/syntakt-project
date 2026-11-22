/* Mod SDK: shared definitions for mods on the Syntakt, OS 1.41. Include it as "syntakt.h".
 *
 * The C rules for a mod, in short:
 *  - No libc. Do not call printf, memcpy, malloc or similar. Write the loop yourself.
 *  - No libgcc helpers. Avoid 64-bit maths and calls the compiler turns into helpers. The build refuses
 *    a mod that calls one.
 *  - No .bss. Give every global variable DATA and a start value that is not zero, for example
 *    DATA u32 count = 1;  A zero start can end up in .bss, which the build refuses.
 *  - Do not write exg. Use movem only with (An) or d16(An) addressing.
 *  - Short branches (bra.s, bne.s) reach only 127 bytes. The compiler picks the form; if you write
 *    assembly yourself, use the long form for far targets.
 *  - Save every register you use. The compiler does this for C functions.
 *  - A hook replaces some stock instructions. Those instructions are gone, so your function must do
 *    their work itself before it returns.
 */

#ifndef SYNTAKT_H
#define SYNTAKT_H

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int s32;

/* Put a global variable in the .data section (the mod's own data). */
#define DATA __attribute__((section(".data")))

/* The digital tracks routed to the analog FX block, L/R interleaved, FRAMES frames.
 * SyntHack's docs name 0x8000DFD0 for this bus, but on the unit the two buses are swapped:
 * 0x8000DAD0 is the one that reaches the FX block. */
#define FX_BUS ((s32 *)0x8000DAD0u)
#define FRAMES 32

#endif
