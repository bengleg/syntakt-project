# Syntakt custom firmware: DelayCtrl, DJ filter, Drive rectifier

Version v2o. Built for **Syntakt OS 1.41 only**. Unofficial hobby firmware, not
affiliated with or supported by Elektron.

## Getting the firmware

Download the ready-built file from [Releases](https://github.com/bengleg/syntakt-project/releases)
and flash it, or build it yourself from your own stock OS file — see
[Install it on your Syntakt](README.md#install-it-on-your-syntakt). It is the same firmware either way.

## What it changes

Three things, plus a rearranged FX page:

1. **DelayCtrl** takes over MOD B and turns it into an Octatrack-style freeze and repeat. The delay effect is hijacked while it's selected.
2. **DJ filter** replaces the LP-Notch choice in the FX filter's TYPE list.
3. **Drive rectifier** is mixed into the FX block's Drive above 5.
4. **FX SYN page** holds reverb, filter and send controls instead of its old layout.

Everything else on the machine works as before.

## DelayCtrl (MOD B)

Select MOD B with `FUNC` + `TRIG 16` and the screen says "DelayCtrl ON". Pick any
other modifier and it turns off again.

While it's on, the stock delay is silent. Sends, p-locks and LFOs aimed at the
delay have no effect, and the delay comes back untouched when you leave. Nothing
gets written into your pattern.

Hold `TRIG 13` to `16` to freeze. The last beat of everything going through the
FX block starts looping, in time: 13 is 1/4, 14 is 1/8, 15 is 1/16, 16 is 1/32.
While holding a slower key, hit a faster one and the loop chops down to the
latest part and stays there until you let go. Release everything and the normal
sound is back immediately. Short fades at the edges keep it click-free.

Only sounds routed to the FX block are frozen, so digital tracks 1-8, analog 9-12
set to route through the FX block, and the external input if you've routed it.
The rest of the kit keeps playing, which is what makes it usable in a mix. The
loop still passes through the analog Drive and filter, so those still shape it.

### Loop rates

The four keys aren't stuck at 1/4 to 1/32. Open the DCTL setup page (`FUNC` +
`TRIG 16`, then `FUNC` + up/down) and the four slots use the RETRIG look, with
the usual boxes. You get 1/4, 1/6, 1/8, 1/12, 1/16, 1/24, 1/32, 1/48 and 1/64.
Whatever you pick is what that key plays. The DEST slot is gone from that page.

If you're coming from an older version of this firmware, your project still holds
values from the old range, so the boxes may read something odd at first. Set them
once and they behave.

## DJ filter

In the FX track's filter page, the TYPE list gets **DJ** where LP-Notch used to
be. It's one knob: FREQ below the middle is a 2-pole lowpass that opens up until
it's fully open at 63, and above the middle it's a 2-pole highpass that closes in
again. RESO and filter pan work like they always did, and the curve drawing flips
between the two.

The analog tracks share the same type list, so their seventh type is also
labelled DJ, but it's still the real LP-Notch underneath.

## Drive rectifier

On the FX block's Drive, anything above 5 blends in a full-wave rectifier, clean
at 5 and fully rectified at 11. The analog drive still stacks on top. It only
applies to digital tracks going through the FX block, not analog tracks or the
external input.

## FX SYN page

| Slot | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Control | Reverb HPF | Reverb LPF | Reverb Decay | Reverb Send | Filter FREQ | Filter RESO | Filter Pan | Drive |

Slots 5 and 6 are the filter page's FREQ and RESO, and slot 7 is its pan. They're
the real parameters, so p-locks and saving work normally.

## Known limits

- OS 1.41 only. Nothing else will work.
- One beat is the longest loop. No multi-bar stuff.
- DJ FREQ has no snap points, so `FUNC` + turn just jumps to the end.
- SYN slots 1-2 and 5-6 draw as plain knobs, not as pictures.
- The delay page isn't greyed out while DelayCtrl is on, it's just silent.
- Leaving DelayCtrl with very high delay feedback can briefly bring back old echoes.
- A frozen analog track can come out at a slightly different level than normal.
- There's a small click when the DJ filter crosses from lowpass to highpass.
- While you're holding a DelayCtrl key, `TRIG 1-12` still plays its normal sound.
- This build can't be combined with the beat-repeat mod, since both live in the same place.

## Installing, and getting out again

You need a Syntakt on OS 1.41, Elektron Transfer, and a **MIDI DIN interface**
(5-pin MIDI OUT) for recovery. USB doesn't work from the startup menu, so if you
don't have a DIN interface, don't flash this.

Back up your projects first. Flash the firmware with Transfer's drop page. Then
`FUNC` + `TRIG 16` for DelayCtrl.

If the machine won't boot or starts crashing, hold `FUNC` while powering on to
reach the startup menu, press `TRIG 4` for OS UPGRADE (not TRIG 2 or 3, those
erase data), and send the official 1.41 file with Transfer over the DIN
interface. Expect tens of minutes and let it finish. Flashing the official 1.41
the normal way also puts the machine back to stock whenever you want.

## Risk and legal

Modified firmware can leave the unit unusable and can void the warranty. Use it
at your own risk.

Nothing Elektron ships is stored in the repository. Both the release file and a
self-built file are made from your own official OS 1.41 file. The bootloader is
untouched, which is what makes recovery possible.

This sits on top of the open-source SyntHack project (MIT) and its tools.
This repository: https://github.com/bengleg/syntakt-project
