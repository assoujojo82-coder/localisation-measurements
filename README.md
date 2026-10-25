# Localisation measurements

Four checks that decide whether an open-weight dubbing or live-interpretation
pipeline produces something usable — and a fifth file that reproduces every
claim in this README in one command.

```bash
python verifier.py
#   78/78 cases pass
#   Exit codes and the hand-calculated numbers all match.
```

No dependencies. Standard library only, no network, nothing written outside a
temporary directory. Python 3.8+.

## Why measurements and not another pipeline

Wiring Whisper to a text-to-speech model is a weekend. The problem is that the
output of that weekend is quietly unusable, and watching it once will not tell
you. Three things go wrong and none of them look like a bug:

**The translation is correct and it is twenty per cent too long.** English into
French, German or Spanish typically expands by 15–25 %. The line is right; it
cannot be said in the time the mouth is open.

**The live interpreter falls behind, and keeps falling behind.** If translated
speech takes longer to say than the original, every sentence widens the gap.
Two seconds behind at minute one, forty at minute thirty. A five-minute demo
never shows it.

**A figure arrives altered and nobody questions it.** A dropped sentence gets
noticed. "Forty-five thousand" becoming "fifty-four thousand" arrives in the
same confident tone as everything else, and goes into the minutes.

## The four tools

### `ajuster_doublage.py` — does the line fit the mouth?

```bash
python localisation/ajuster_doublage.py segments.json
python localisation/ajuster_doublage.py segments.json --modele caracteres --json
```

Estimates how long each translated line takes to speak, compares it with the
time available, and classifies: fits, fits only with a time-stretch under the
audible ceiling, too short (the mouth keeps moving after the line ends), or
must be shortened — with how much to cut, in syllables and in milliseconds.
Also catches what no rewriting fixes: one character in two overlapping
segments, a character cast to two voices, one voice doing two characters.

At 5 syllables/second, a 14-syllable line in a 2 000 ms gap:

```
[bloquant ] 2: 1.40x too long for the time available
             (2800 ms of speech in 2000 ms): cut about 4 syll, or 680 ms
```

It says *that* four syllables must go. It will not choose which four:
shortening a line while keeping the character's register is writing.

**Calibrate the rate.** The shipped defaults are starting points. Measure your
own voice on twenty real lines and put it in `debit`; the tool prints
`DEFAULT - calibrate it` until you do, because a figure with two decimals built
on a borrowed rate is a guess wearing a uniform.

### `valider_sous_titres.py` — timed text a broadcaster will accept

```bash
python localisation/valider_sous_titres.py subs.srt --langue fr --fps 25
python localisation/valider_sous_titres.py subs.vtt --duree 5400 --json
```

SubRip and WebVTT. Timecode format and reality (`20260230` passes a regex and
fails a calendar), order, overlap, the minimum gap between cues — two touching
cues flicker into one — duration floor and ceiling, **reading speed** in
characters per second against the target language's limit, line length, line
count, duplicate cue numbers, cues past the end of the media. Findings graded
`bloquant` / `majeur` / `mineur`.

### `budget_latence.py` — latency, and the drift nobody computes

```bash
python localisation/budget_latence.py budget.json
```

Sums the stages you measured; reports the median, a **p95 estimate for
independent stages** and the worst case; names the stage to cut and by how
much. Then computes drift from the expansion ratio and the two speaking rates,
in seconds per minute and over half an hour, and says what the synthesis would
have to deliver to break even.

Two points worth the file on their own:

**Summing each stage's p95 is the worst case, not the p95.** It assumes every
stage has its bad day at the same instant. If the stages are independent the
real p95 sits near the median plus the combined spread. Design on the
pessimistic figure only when the stages share a cause — one GPU, one thermal
limit.

**Drift is arithmetic.** Each second of speech costs
`expansion × source_rate / tts_rate` seconds to deliver. At expansion 1.25 with
equal rates and 60 % speech, that is +9 s per minute — 270 s after half an
hour. No model upgrade fixes it; you speak faster, compress, or switch to
subtitles, and you decide which before the meeting.

### `glossaire_terminologie.py` — terminology held, figures carried

```bash
python localisation/glossaire_terminologie.py glossary.json transcript.json
```

Checks the mandated rendering is used, that forbidden renderings are not, that
the term is rendered the same way **across the whole meeting** rather than
inside one segment, that it was not simply left in the source language, and
that every figure in the source appears in the target.

It distinguishes a figure **dropped**, **altered** and **invented** — an
altered number sounds right and nobody reopens it. Accent- and
case-insensitive, and tolerant of thousands separators, so `1 200 000`,
`1.200.000` and `1200000` are the same figure while a changed digit still
shows.

## Models, and their licences

Open weights are not one licence, and two of them change what you may build.
**Verified on 25 October 2026**, with what was not verified marked as such, in
[MODELS.md](MODELS.md). The short version:

- **NLLB-200 is CC-BY-NC 4.0** — no commercial use. Excellent coverage, and it
  cannot sit inside anything you charge for.
- **Opus-MT is Apache-2.0**, which is why it is the default here.
- **Piper's maintained release is GPL-3.0** — run it as a separate process
  rather than importing it, and read the voices' own licences, which often
  differ from the engine's.

## Provenance and timeline

The challenge rules ask that non-trivial prior work be credited, so here it is,
dated.

The four measurements in `localisation/` were written on **25 October 2026**,
the day before the Week 4 window opened, as the tested scripts behind two
commercial skills in a catalogue I maintain. They are reused here under
AGPL-3.0 by their copyright holder. That is the prior work, and the commit
dates in this repository will show it rather than hide it.

What is built **inside** the window (26-31 October 2026) is the pipeline that
these measurements gate: stem separation, streaming transcription, translation,
line adaptation, synthesis and the mix. Any commit after the deadline will be
noted here, as the rules require.

If a judge wants the line between the two, it is exactly this: everything that
runs without a model was written before, everything that needs a model was
written during.

## What is here, and what is not

In this repository: the four measurements, and `verifier.py` which reproduces
all 78 cases.

Not in this repository, and deliberately: no model weights, no media, and no
pipeline that claims to work without being run against real models. The
dubbing and interpretation commands are being built during the Hacktoberfest
Week 4 window (26–31 October 2026); until each stage has run end to end against
real audio, it is not in here claiming otherwise.

## What this will not do, even finished

It produces a **draft**. Correct timing, consistent voices, clean stems, and a
list of lines a human must rewrite. A broadcast dub also has an adapter who
rewrites for the mouth, a director, actors and a mix engineer. Live
interpretation here carries content with a measured delay and a known error
rate; a human interpreter carries intent, register, and the thing that was
meant and not said.

Good enough for internal video, training material, conferences, accessibility
and long-tail languages. Not good enough where the words bind someone — a
contract, a medical consultation, an HR matter. There it is a comprehension aid
sitting beside a human interpreter, and the output should say so.

**One rule is not negotiable:** do not clone an identifiable person's voice
without their written consent. A synthetic voice that imitates someone is that
person's likeness.

## Licence

**[AGPL-3.0](LICENSE)** for the code in this repository.

That choice is deliberate and it has a consequence worth stating plainly:
section 13 means that if you offer a modified version of this **over a
network**, the people using it are entitled to your source. A permissive
licence would let a closed service absorb these checks and give nothing back,
and measurement work is exactly the kind of thing that should stay inspectable.

If you want it in a closed product or a closed service, ask the copyright
holder for other terms — that is a normal request, not an imposition.

The models you plug in carry their own licences, and some forbid commercial
use whatever this repository says: see [MODELS.md](MODELS.md).
