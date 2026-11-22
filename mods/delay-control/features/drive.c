/* Drive rectifier: a full-wave rectifier ahead of the analog FX Drive, on the same bus (digital tracks routed to
 * the FX block). No hook of its own: the shared runtime's mix hook calls dc_drive_run through DC_REG_DRIVE.
 * DRIVE (FX track, engine copy 0x800028F0, 0..0x7F00, shown 0..11): stock below 5, then a linear blend from
 * clean at 5 to fully rectified (|x|) at 11. No DC removal (by request).
 */

#include "dc.h"

#define DRIVE    (*(const volatile unsigned short *)0x800028F0u)
#define DRV_LO   (0x7F00u * 5 / 11)                    /* display 5 */
#define DRV_HI   0x7F00u                               /* display 11 */

void dc_drive_run(void)
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
