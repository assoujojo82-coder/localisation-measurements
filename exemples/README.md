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

---

# Then: can a local model fix the lines the measurement rejected?

```bash
ollama pull gemma3:4b
python exemples/adapter_avec_gemma.py
```

Four lines were rejected as too long. Shortening a line while keeping its
register is the one step a script cannot do, so this is where a model earns
its place. **Gemma 3 4B, through Ollama, on this laptop.** It took three
attempts to get the loop right, and both failures are worth more than the
final number.

## Attempt 1 — ask the model for a syllable budget: 0 of 4

The obvious design: "rewrite this in at most 4 syllables", three tries, keep
the best.

```
[001] avant ( 9 syll) On devrait y aller maintenant.
      apres ( 5 syll) Allons-y, ca va.              -> 1.32x  TOUJOURS TROP LONG
[002] avant (10 syll) Je t'avais dit que ca arriverait.
      apres (12 syll) Je t'avais prevenu que ca se produirait.  -> 1.81x
```

**Nothing fit, and line 002 came back longer than it went in.** A language
model does not count syllables, so asking it to respect a syllable budget asks
for the one thing it cannot do.

## Attempt 2 — ask for variants, let the counter pick: 4 of 4, and still wrong

Same model, different architecture: ask for six variants from closest to most
elliptical, measure each, keep the best. Suddenly all four "fit".

Except two of them fit by being **far too short** — 0.53x and 0.70x, under the
0.80 floor this project defines, with the mouth still moving after the line is
over. The selection rule was "shortest wins", which does not fix *too long*,
it trades it for *too short*.

**A criterion that reports success for the wrong reason is worse than one that
reports failure.** That bug was in my own code, and the only thing that
surfaced it was reading the ratios instead of the verdict.

## Attempt 3 — select inside the acceptable window: 3 of 4

The window is `plancher` to `1 + tolerance`, here 0.80x to 1.06x, and inside
it the variant that best fills the time wins. Long is penalised harder than
short, because a rushed delivery is heard immediately.

```
fenetre acceptable 0.80x a 1.06x, 6 variantes par appel, 3 appels au plus

[001] 714 ms, 3.0 a 4.0 syllabes
      avant ( 9 syll) On devrait y aller maintenant.
      apres ( 3 syll) On y va.          -> 0.79x  DESORMAIS TROP COURT  (18 variantes)
[002] 1250 ms, 5.3 a 7.0 syllabes
      avant (10 syll) Je t'avais dit que ca arriverait.
      apres ( 7 syll) Ca arrive, je t'avais dit.   -> 1.06x  TIENT
[008] 714 ms, 3.0 a 4.0 syllabes
      avant ( 5 syll) Ce n'etait pas moi.
      apres ( 4 syll) Ce n'est pas moi.            -> 1.06x  TIENT
[011] 2143 ms, 9.1 a 12.0 syllabes
      avant (13 syll) Et les autres, on ne peut pas les abandonner.
      apres (11 syll) Et les autres, on ne les abandonne pas.  -> 0.97x  TIENT

3/4 dans la fenetre apres adaptation
```

**Three of four, and the fourth is honestly refused.** Line 001 has 714 ms for
three to four syllables; across 18 measured variants the model never found one
that both fits and fills it. That line goes to a human, which is the correct
outcome, and it is the outcome a pipeline that trusted the model would have
hidden.

## What is still wrong with the three that passed

Read them, do not just count them.

- **[008]** "Ce n'etait pas moi." became "Ce n'est pas moi." — past to present.
  It fits and it is a different statement. A timing check cannot catch that.
- **[002]** "Ca arrive, je t'avais dit." is colloquial to the point of being
  clipped; whether it suits the character is a judgement about the film.
- **[011]** is the only one I would ship without argument.

So the loop produces **candidates worth reviewing**, not finished dialogue.
That is what "the model proposes, the measurement disposes, the human decides"
means in practice, and it is why the tool prints what it changed rather than
quietly writing it back.

## Cost

Everything above ran on one laptop: Opus-MT (~300 MB) and Gemma 3 4B (3.4 GB)
on an RTX 4060 Laptop, no account, no per-minute billing, no audio leaving the
machine. That is the argument for open weights, in a form you can re-run.
