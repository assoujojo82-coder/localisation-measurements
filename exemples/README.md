# A measurement that corrected me

Run on **25 October 2026** against a real open-weight model, to check the
claim this project was built on.

```bash
python exemples/mesurer_expansion.py          # needs torch + transformers
python localisation/ajuster_doublage.py exemples/segments-opusmt.json
```

The first command translates twelve lines of plain film dialogue with
**Opus-MT en→fr** (`Helsinki-NLP/opus-mt-en-fr`, Apache-2.0, running locally)
and writes `segments-opusmt.json`. The second measures whether those
translations fit.

## What I expected, and what I got

The figure everyone repeats is that English expands by **15–25 %** into
French. I had written it into my own documentation.

Measured on these twelve lines: **102 English syllables became 98 French ones.
An aggregate of 0.96 — no expansion at all.**

If I had stopped there I would have concluded the problem does not exist. Then
the per-line check:

```
  id    speaker        avail  spoken  ratio  state
  001   ANNA             714    1698   2.38  a_raccourcir
  002   BORIS           1250    1887   1.51  a_raccourcir
  003   ANNA            1965    1887   0.96  tient
  004   BORIS           1607    1132   0.70  trop_court
  005   ANNA            1785    1509   0.84  tient
  006   BORIS           1608    1698   1.06  etirement
  007   ANNA            1607    1509   0.94  tient
  008   BORIS            714     943   1.32  a_raccourcir
  009   ANNA            1071    1132   1.06  etirement
  010   BORIS           1965    1698   0.86  tient
  011   ANNA            2143    2453   1.15  a_raccourcir
  012   BORIS           1785     943   0.53  trop_court

  tient 4 · etirement 2 · trop_court 2 · a_raccourcir 4
  1873 ms to recover in all, by rewriting.
```

**Four lines out of twelve fit.** Four need shortening — one of them by
**2.38×**, because "We should go now." came back as "On devrait y aller
maintenant." Two are too short. Two only fit with a time-stretch.

So the average was not merely imprecise, it pointed the wrong way. A pipeline
that checked mean expansion would have reported "French is slightly shorter,
we are fine" and shipped eight bad lines out of twelve.

**The dispersion is the job.** That is the finding, and it is why a per-line
check exists instead of a rule of thumb.

## A defect the duration check caught without being designed to

Line 012: *"They made their choice. We make ours."* came back as *"Ils ont fait
leur choix."* — the second sentence is **gone**. The translation that remains is
fluent and correct, so nothing downstream would question it.

It surfaces here as `0.53x trop_court`: the line is half the length the shot
needs. A timing check is not a content check, but dropped content makes a line
short, and short lines get looked at. Worth knowing.

## What is real here and what is modelled

Being precise about this, because the distinction decides what the numbers are
worth.

**Real:** the translations. Opus-MT ran locally, on this machine, and
`segments-opusmt.json` is its unedited output.

**Modelled:** the `avail` column. There is no audio in this repository, so each
line's available time is computed from its **English** syllable count at
5.6 syllables/second, the tool's default English dialogue rate. It is not
measured from a recording.

**Therefore** the robust result is the spread of the per-line syllable ratio —
0.5 to 2.25 — which is a property of the real translations and does not depend
on the duration model at all. Against real audio the individual `avail` values
would differ and the states would shift; the dispersion would not go away.

**And** the syllable counter is a vowel-group heuristic accurate to about one
syllable per line, so the ratios near 1.00 carry no resolution. `EXPERT.md`
says do not arbitrate between 0.98 and 1.08, and that applies to this table
too: lines 003, 006, 007 and 009 are "ask the booth". Lines 001 and 012 are
not — 2.38× and 0.53× are far outside the noise.

## Reproducing it

`mesurer_expansion.py` is the only file in this repository that needs anything
installed: **torch** and **transformers**, plus roughly 300 MB of model weights
fetched on first run. Everything in `localisation/` remains standard library
only.

The dialogue is twelve invented lines, written to be ordinary spoken dialogue
rather than anything quotable. Swap them for your own corpus — twenty lines of
your actual material will tell you more about your language pair than any
published figure, including this one.
