> *Internal decision memo from building Astrobserve, published as written (September 2026). File and setting names refer to the private codebase. Note the two dated updates at the top: the final decision changed after the analysis.*

# Which ayanamsa should astrobserve use?

**Date:** 2026-09-21
**Question:** switch the transit builder from `SE_SIDM_LAHIRI` to `SE_SIDM_TRUE_CITRA`?
**Answer:** **no.** `TRUE_CITRA` is six times worse.

**UPDATE 2026-09-21:** the builder was switched to **`SE_SIDM_LAHIRI_VP285`**, the
mode this report recommends, and the table rebuilt. Measured against the same 48
ingresses afterwards: median 4.01 min (was 4.8), worst 27.01 min (was 47.8),
**zero date disagreements** (was 1). The "astrobserve now" column below is the
state *before* that change; the "with VP285" column is what ships today.

Everything below can be checked by hand against a public website. No code required.

**UPDATE 2026-09-27: back to `SE_SIDM_LAHIRI`**, so the transit table reads the
birth chart's zodiac. The table below shows Drik lying *between* the two (Sun
ingresses −5 min under Lahiri, +4 under VP285), so it could not decide between
them; Lahiri's standing as the official standard and its closer fit to its own
definition (Spica at 180°: 57.8″ short against 80.7″) did. The one date that
disagrees again is Mars into Taurus 2026, displayed as 21 June only because the
table rounds 23:59:36 to the minute. Reasons in full: `build_transit_ephemeris.js`.

---

## How to verify this yourself

1. Open **https://www.drikpanchang.com/planet/transit/surya-transit-date-time.html**
   and set the year to 2026. Same page for the other planets — swap `surya` for
   `budha` (Mercury), `shukra` (Venus), `mangal` (Mars), `guru` (Jupiter).
2. Drik gives each sign change in **local New Delhi time (IST)**, 12-hour clock.
   Its setting is *Lahiri/Chitra Paksha*, the same family we use.
3. Compare against the "astrobserve now" column below.
4. For positions rather than ingresses, use
   **https://www.drikpanchang.com/planet/position/planetary-positions-sidereal.html** —
   read the **DMS column** (`04° Kany 10′ 58″`), not the "Full Degree" decimal.
   Drik **truncates** that decimal, by up to 24″, which will mislead you.

---

## Result: three ayanamsas against all 48 of Drik's 2026 ingresses

| Ayanamsa | Median error | Worst error | Ingresses off by >30 min | **Wrong calendar date** |
|---|---|---|---|---|
| `SE_SIDM_LAHIRI` — what we use | 4.8 min | 47.8 min | 2 | **1** |
| `SE_SIDM_LAHIRI_VP285` | **4.1 min** | **26.9 min** | **0** | **0** |
| `SE_SIDM_TRUE_CITRA` — proposed | 24.9 min | **300.1 min** | 17 | 1 |

`TRUE_CITRA` puts one ingress **five hours** from Drik's time and misses 17 of 48
by more than half an hour. It is not the mode Drik is using.

### The one date that currently disagrees

> **Mars enters Taurus.**
> Drik Panchang: **21 June 2026, 12:07 AM**
> astrobserve: **20 June 2026, 11:59 PM**
> *Different day.* With `VP285`: 21 June, 12:12 AM — agrees.

This is the near-midnight case. A user checking Mars's Taurus transit against
Drik today would see a one-day difference.

There is a wrinkle worth knowing: the shipped table stores ingress times rounded
to the minute, and that rounding pushes 23:59:36 up to 00:00 on the 21st. So the
**displayed** date in the app is currently right, by a 24-second accident. The
underlying calculation is on the wrong side of midnight.

---

## The full table — every 2026 ingress

Times are IST. "diff" is astrobserve minus Drik, in minutes; negative means we
are early.

| Planet | Enters | Drik Panchang | astrobserve now | diff | with VP285 | diff |
|---|---|---|---|---|---|---|
| Sun | Capricorn | 14 Jan 03:13 PM | 14 Jan 03:07 PM | &minus;6m | 14 Jan 03:16 PM | +3m |
| Sun | Aquarius | 13 Feb 04:14 AM | 13 Feb 04:08 AM | &minus;5m | 13 Feb 04:18 AM | +4m |
| Sun | Pisces | 15 Mar 01:08 AM | 15 Mar 01:03 AM | &minus;5m | 15 Mar 01:12 AM | +4m |
| Sun | Aries | 14 Apr 09:38 AM | 14 Apr 09:32 AM | &minus;5m | 14 Apr 09:42 AM | +4m |
| Sun | Taurus | 15 May 06:28 AM | 15 May 06:22 AM | &minus;6m | 15 May 06:31 AM | +4m |
| Sun | Gemini | 15 Jun 12:58 PM | 15 Jun 12:53 PM | &minus;5m | 15 Jun 01:02 PM | +5m |
| Sun | Cancer | 16 Jul 11:44 PM | 16 Jul 11:39 PM | &minus;5m | 16 Jul 11:49 PM | +5m |
| Sun | Leo | 17 Aug 08:03 AM | 17 Aug 07:58 AM | &minus;4m | 17 Aug 08:08 AM | +5m |
| Sun | Virgo | 17 Sep 07:58 AM | 17 Sep 07:52 AM | &minus;5m | 17 Sep 08:02 AM | +4m |
| Sun | Libra | 17 Oct 07:57 PM | 17 Oct 07:51 PM | &minus;5m | 17 Oct 08:00 PM | +4m |
| Sun | Scorpio | 16 Nov 07:48 PM | 16 Nov 07:43 PM | &minus;5m | 16 Nov 07:52 PM | +4m |
| Sun | Sagittarius | 16 Dec 10:29 AM | 16 Dec 10:25 AM | &minus;4m | 16 Dec 10:34 AM | +5m |
| Mercury | Capricorn | 17 Jan 10:27 AM | 17 Jan 10:24 AM | &minus;3m | 17 Jan 10:29 AM | +3m |
| Mercury | Aquarius | 3 Feb 09:54 PM | 3 Feb 09:52 PM | &minus;2m | 3 Feb 09:57 PM | +3m |
| Mercury | Pisces | 11 Apr 01:20 AM | 11 Apr 01:16 AM | &minus;4m | 11 Apr 01:23 AM | +3m |
| Mercury | Aries | 30 Apr 06:55 AM | 30 Apr 06:52 AM | &minus;2m | 30 Apr 06:57 AM | +3m |
| Mercury | Taurus | 15 May 12:34 AM | 15 May 12:32 AM | &minus;2m | 15 May 12:36 AM | +2m |
| Mercury | Gemini | 29 May 11:14 AM | 29 May 11:11 AM | &minus;2m | 29 May 11:16 AM | +3m |
| Mercury | Cancer | 22 Jun 03:41 PM | 22 Jun 03:30 PM | &minus;10m | 22 Jun 03:47 PM | +7m |
| Mercury | Gemini *(retro)* | 7 Jul 10:32 AM | 7 Jul 10:46 AM | +14m | 7 Jul 10:28 AM | &minus;4m |
| Mercury | Cancer | 5 Aug 07:58 PM | 5 Aug 07:54 PM | &minus;4m | 5 Aug 08:01 PM | +4m |
| Mercury | Leo | 22 Aug 07:33 PM | 22 Aug 07:31 PM | &minus;1m | 22 Aug 07:36 PM | +3m |
| Mercury | Virgo | 7 Sep 01:35 PM | 7 Sep 01:32 PM | &minus;2m | 7 Sep 01:38 PM | +3m |
| Mercury | Libra | 26 Sep 12:41 PM | 26 Sep 12:38 PM | &minus;2m | 26 Sep 12:45 PM | +4m |
| Mercury | Scorpio | 2 Dec 05:30 PM | 2 Dec 05:27 PM | &minus;2m | 2 Dec 05:33 PM | +4m |
| Mercury | Sagittarius | 22 Dec 07:42 AM | 22 Dec 07:39 AM | &minus;2m | 22 Dec 07:45 AM | +4m |
| Venus | Capricorn | 13 Jan 04:02 AM | 13 Jan 03:58 AM | &minus;4m | 13 Jan 04:05 AM | +3m |
| Venus | Aquarius | 6 Feb 01:15 AM | 6 Feb 01:11 AM | &minus;3m | 6 Feb 01:18 AM | +4m |
| Venus | Pisces | 2 Mar 01:01 AM | 2 Mar 12:57 AM | &minus;4m | 2 Mar 01:04 AM | +3m |
| Venus | Aries | 26 Mar 05:13 AM | 26 Mar 05:09 AM | &minus;4m | 26 Mar 05:16 AM | +4m |
| Venus | Taurus | 19 Apr 03:51 PM | 19 Apr 03:46 PM | &minus;4m | 19 Apr 03:54 PM | +3m |
| Venus | Gemini | 14 May 10:58 AM | 14 May 10:53 AM | &minus;4m | 14 May 11:01 AM | +3m |
| Venus | Cancer | 8 Jun 05:47 PM | 8 Jun 05:43 PM | &minus;4m | 8 Jun 05:50 PM | +4m |
| Venus | Leo | 4 Jul 07:18 PM | 4 Jul 07:13 PM | &minus;4m | 4 Jul 07:22 PM | +4m |
| Venus | Virgo | 1 Aug 09:33 AM | 1 Aug 09:28 AM | &minus;5m | 1 Aug 09:37 AM | +4m |
| Venus | Libra | 2 Sep 01:51 PM | 2 Sep 01:44 PM | &minus;6m | 2 Sep 01:56 PM | +5m |
| Venus | Virgo *(retro)* | 6 Nov 12:45 AM | 6 Nov 01:04 AM | +19m | 6 Nov 12:36 AM | &minus;8m |
| Venus | Libra | 22 Nov 05:38 PM | 22 Nov 05:21 PM | &minus;17m | 22 Nov 05:50 PM | +12m |
| Mars | Capricorn | 16 Jan 04:36 AM | 16 Jan 04:28 AM | &minus;7m | 16 Jan 04:40 AM | +4m |
| Mars | Aquarius | 23 Feb 11:57 AM | 23 Feb 11:50 AM | &minus;7m | 23 Feb 12:02 PM | +5m |
| Mars | Pisces | 2 Apr 03:37 PM | 2 Apr 03:29 PM | &minus;7m | 2 Apr 03:41 PM | +4m |
| Mars | Aries | 11 May 12:47 PM | 11 May 12:38 PM | &minus;8m | 11 May 12:50 PM | +4m |
| **Mars** | **Taurus** | **21 Jun 12:07 AM** | **20 Jun 11:59 PM** | **&minus;7m** | **21 Jun 12:12 AM** | **+5m** |
| Mars | Gemini | 2 Aug 10:59 PM | 2 Aug 10:51 PM | &minus;8m | 2 Aug 11:05 PM | +6m |
| Mars | Cancer | 18 Sep 04:44 PM | 18 Sep 04:35 PM | &minus;8m | 18 Sep 04:50 PM | +7m |
| Mars | Leo | 12 Nov 08:30 PM | 12 Nov 08:18 PM | &minus;11m | 12 Nov 08:38 PM | +9m |
| Jupiter | Cancer | 2 Jun 02:25 AM | 2 Jun 01:50 AM | &minus;35m | 2 Jun 02:38 AM | +14m |
| Jupiter | Leo | 31 Oct 12:50 PM | 31 Oct 12:02 PM | &minus;48m | 31 Oct 01:16 PM | +27m |

Saturn has no sign change in 2026. Rahu and Ketu are excluded: Drik's node pages
list two crossings ten days apart, which is *true*-node wobble, while astrobserve
uses the *mean* node. That is a separate question, not an error.

---

## This was already known

`scripts/build_transit_ephemeris.js` documents the offset at line 24, measured
September 2026 and **deliberately not corrected**. It records the same figures
this report re-derived independently — "~0.0034 deg (~12\")", "Moon 0 min |
Mercury -2 | Sun -5 | Mars -8 | Jupiter -41 to -48" — establishes it is not
light-time or aberration (removing those makes it worse, mean 10 → 26 min), and
notes that VP285 "roughly halves it but overshoots the other way and costs the
Moon's exact match."

So the decision to stay on `SE_SIDM_LAHIRI` was made with evidence, not by
default. What this report adds:

- **`TRUE_CITRA` measured.** The existing note does not mention it. It is 90″
  from Drik against LAHIRI's 14″, and it is disqualified.
- **A date that actually flips.** The note says only an ingress within ~48 min of
  midnight can shift a date. One does: Mars into Taurus, 2026.
- **The Moon cost, quantified.** See below — it is smaller than the note implies.
- **Drik truncates its decimal column**, which makes a casual position comparison
  look worse than it is.

## The Moon — 160 ingresses, the whole of 2026

The note's reason for staying put was the Moon. Tested against Drik's Chandra
gochar page, all 160 sign changes in 2026:

| Mode | Median | Worst | Wrong date |
|---|---|---|---|
| `LAHIRI` — current | 1.10 min | 1.76 min | 0 |
| `LAHIRI_VP285` | 1.79 min | 2.55 min | 0 |
| `TRUE_CITRA` | 0.60 min | 1.93 min | **1** |

The Moon cost of moving to VP285 is real but small: 1.10 min becomes 1.79 min,
worst case 1.76 becomes 2.55. Both stay under three minutes and both produce zero
date disagreements across 160 ingresses. Weighed against Jupiter going from 48
minutes to 27 and the Mars date being fixed, the Moon is not a strong reason to
stay.

> **That caveat is now resolved.** `TRUE_CITRA`'s Moon figure looked anomalous
> because two errors cancel there: its ayanamsa runs the Moon ~2.5 min early,
> and the Moshier lunar theory runs it ~1.9 min late. The Moon is the only body
> carrying a large lunar-theory error, so the cancellation happens nowhere else.
> It is not accuracy. Worked through in `MOON_TRANSIT_ERROR_REPORT.md`, which
> tests all 47 frameworks and fits ayanamsa against error to within 0.4% of
> theory. `TRUE_CITRA` also produces a wrong date the Moon's other contenders
> do not.

---

## Why the errors look the way they do

Every difference scales inversely with how fast the planet moves. The Sun is out
by 5 minutes, Mars by 7, Jupiter by 35&ndash;48. Divide each by that planet's
daily motion and they all reduce to the same thing: **a constant offset of about
14 arcseconds in position**.

That is an ayanamsa difference, not an ephemeris error. Confirmed on positions
for 21 Sep 2026, 14:47:26 IST, against Drik's DMS column:

| Body | astrobserve | Drik Panchang | diff |
|---|---|---|---|
| Sun | 154.186521 | 154.182778 | +13.5&Prime; |
| Mars | 91.764960 | 91.761111 | +13.9&Prime; |
| Mercury | 172.839148 | 172.835833 | +11.9&Prime; |
| Jupiter | 113.576456 | 113.572500 | +14.2&Prime; |
| Venus | 191.724318 | 191.720000 | +15.5&Prime; |
| Saturn | 348.085535 | 348.081111 | +15.9&Prime; |
| Moon | 271.771510 | 271.776667 | &minus;18.6&Prime; |
| Rahu | 303.991501 | 303.984722 | +24.4&Prime; |

Six bodies cluster at **+12″ to +16″** — a uniform shift, which is what an
ayanamsa difference produces and what an ephemeris difference does not.

The Moon's &minus;18.6″ is not a position error: the Moon moves 0.55″ per second,
so that is 34 seconds of clock between Drik rendering its page and our
calculation. Rahu's +24.4″ is a mean-node formula difference and needs its own
look.

---

## What the ayanamsa numbers actually are

For 21 Sep 2026:

```
SE_SIDM_LAHIRI        24.230378°     what we use       14.0" from Drik
SE_SIDM_LAHIRI_VP285  24.236765°     candidate          9.0" from Drik
SE_SIDM_LAHIRI_ICRC   24.230075°                       15.1" from Drik
SE_SIDM_LAHIRI_1940   24.215609°                       67.2" from Drik
SE_SIDM_TRUE_CITRA    24.209184°     proposed          90.3" from Drik
```

Drik's implied value is **24.234267°**. No sweph mode matches it exactly. Drik
evidently uses its own Lahiri implementation, so an exact match is not available
from a mode change alone.

---

## Recommendation

**Do not switch to `TRUE_CITRA`.** It is further from Drik than what we have, by
a factor of six, and it would introduce 17 ingresses that disagree by more than
half an hour.

**`SE_SIDM_LAHIRI_VP285` is a genuine improvement** on every measure: median
4.1 min against 4.8, worst case 27 min against 48, zero ingresses over half an
hour against two, and it fixes the Mars-into-Taurus date. Note that the residual
changes sign — we would be 3&ndash;5 minutes *late* rather than 5 minutes early.

Switching means rebuilding `data/transit-ephemeris.js` with the new mode
(`node scripts/build_transit_ephemeris.js`, needs `sweph`) and re-running the
verification. It also shifts every chart the dev-server computes. It does **not**
affect production birth charts, which come from FreeAstrologyAPI and are still
unchecked against any of this.

**Done.** The builder uses `SE_SIDM_LAHIRI_VP285` and the table has been rebuilt.

**2026-09-25 — the last holdout followed.** `scripts/shadbala/context.js`
still defaulted to plain `SE_SIDM_LAHIRI`, so the shadbala verifier and
the app were running zodiacs 23.0″ apart — the same magnitude this
document measures. It now defaults to `SE_SIDM_LAHIRI_VP285`, and the
repo uses one ayanamsa throughout.

Cost of aligning, measured over 8 charts × 7 planets: **0 sign changes,
0 nakshatra changes, 1 varga-dignity change** (Vaibhav Bhagat's Saturn,
navamsa Scorpio → Libra), worth 26.25 virupas of Sthana. Mean |Δ| on the
total is 0.47. Agreement with AstroSage and JagannathaHora moved by
0.3–0.5 virupas — slightly *away*, since both appear to use plain Lahiri.
That is the expected price of preferring Drik Panchang (9.0″) over
matching competitors (14.0″).
