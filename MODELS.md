# Model licences

"Open source" is not a licence, and open weights are not one licence. Two of
the models a localisation pipeline reaches for first will change what you are
allowed to build with it.

Checked **25 October 2026**. Where a licence was not read at source it is
marked **not verified** rather than assumed — a licence table that guesses is
worse than no table.

## Verified at source, 25 October 2026

| Component | Licence | Commercial use | Read at |
|---|---|---|---|
| **Opus-MT** (Helsinki-NLP, Marian) | Apache-2.0 | Yes | model card, `Helsinki-NLP/opus-mt-en-fr` |
| **NLLB-200** (Meta) | **CC-BY-NC 4.0** | **No** | model licence file + several secondary sources |
| **Demucs** (Meta) | MIT | Yes | repository: "released under the MIT license" |
| **Piper**, 2023 code (`rhasspy/piper`) | MIT | Yes | repository — **archived, development moved** |
| **Piper**, maintained (`OHF-Voice/piper1-gpl`) | **GPL-3.0** | Yes, with copyleft | repository |

## Not verified — confirm before shipping

| Component | Commonly stated | Why you must check it yourself |
|---|---|---|
| faster-whisper / CTranslate2 | MIT | Not read at source on this pass |
| Whisper weights (OpenAI) | MIT | Not read at source on this pass |
| Silero VAD | MIT | Not read at source on this pass |
| Gemma | Gemma Terms of Use + Prohibited Use Policy | A bespoke licence with use restrictions, not a standard open licence. Read it. |
| MADLAD-400 | — | Not checked |
| XTTS / Kokoro | — | Not checked; XTTS has had licence changes |
| **Voice models for any TTS engine** | varies per voice | **Almost always licensed separately from the engine.** A voice trained on one speaker's recordings can carry restrictions the MIT engine does not. |

## What this means in practice

**NLLB-200 is the trap.** 200 languages, strong quality, and CC-BY-NC — no
commercial use. It is perfect for a free, open tool and disqualified from
anything you charge for, including an internal tool at a company that sells the
output. That is why **Opus-MT (Apache-2.0) is the default here** and NLLB sits
behind an explicit flag.

**GPL-3.0 is not a problem, it is a boundary.** Invoking `piper` as a separate
process — `subprocess`, a pipe, a CLI call — is ordinary use of a program and
carries no obligation on your code. Importing it as a library into your own
binary does. Pick the process boundary and the question does not arise.

**Weights and code are licensed separately**, and so are individual voices.
"The engine is MIT" tells you nothing about the voice you are about to put in a
client's film.

**Fine-tunes inherit.** A model fine-tuned from NLLB-200 is still
non-commercial, however it is renamed or repackaged.

## How to check one yourself

1. Open the model card or repository and read the `license` field **and** any
   `LICENSE`, `LICENSE.model`, `NOTICE` or terms-of-use file next to it.
2. Check the weights separately from the code, and each voice separately from
   the engine.
3. For a bespoke licence (Gemma, Llama, XTTS), read the acceptable-use or
   prohibited-use policy, not only the licence — the restriction that bites is
   usually there.
4. Record the date you checked. These terms change, and "it was MIT when I
   looked" is only a defence if you can say when you looked.

*Not legal advice. This is what was read, on the date given, with the
unverified rows named as unverified. For anything you are going to charge for,
have it confirmed.*
