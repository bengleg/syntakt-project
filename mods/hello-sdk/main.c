/* Hello SDK: the smallest example mod. It has no hooks, so nothing calls it yet.
 * The function is code; the counter is data (DATA), so the build splits the two.
 * The counter starts at 1, not 0 (see syntakt.h). */
#include "syntakt.h"

DATA u32 hello_calls = 1;

u32 hello_entry(void)
{
    hello_calls++;
    return hello_calls;
}
