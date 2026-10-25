# Copyright (C) 2026 SYNERGIELOC
#
# This file is part of "Localisation measurements".
# Licensed under the GNU Affero General Public License v3 or later.
# See the LICENSE file, or <https://www.gnu.org/licenses/>.
"""Measure, on a real open-weight model, how much a translation expands.

Opus-MT en->fr, Apache-2.0, run locally. The point is not the translation
quality: it is the length. If French takes more syllables to say than the
English it replaces, every dubbed line is at risk, and that is the number the
whole project is built on.

Writes segments.json next to itself so ajuster_doublage.py can be run on it.
"""
import json
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
OUTILS = ICI.parent / 'localisation'
sys.path.insert(0, str(OUTILS))
from ajuster_doublage import syllabes  # noqa: E402

# Twelve lines of plain film dialogue: short, spoken, nothing literary.
LIGNES = [
    ("ANNA",  "We should go now."),
    ("BORIS", "I told you this would happen."),
    ("ANNA",  "Listen to me. There is no time left."),
    ("BORIS", "Who else knows about the money?"),
    ("ANNA",  "Nobody. I made sure of it."),
    ("BORIS", "Then why is he still following us?"),
    ("ANNA",  "Because somebody talked."),
    ("BORIS", "It was not me."),
    ("ANNA",  "I never said it was."),
    ("BORIS", "We have to leave the city tonight."),
    ("ANNA",  "And the others? We cannot just abandon them."),
    ("BORIS", "They made their choice. We make ours."),
]

# Dialogue speaking rates, syllables per second (the tool's own defaults).
DEBIT_EN, DEBIT_FR = 5.6, 5.3


def main():
    from transformers import MarianMTModel, MarianTokenizer
    nom = 'Helsinki-NLP/opus-mt-en-fr'
    print(f'chargement de {nom} (Apache-2.0, local)...', flush=True)
    tok = MarianTokenizer.from_pretrained(nom)
    modele = MarianMTModel.from_pretrained(nom)
    print('  charge\n', flush=True)

    textes = [t for _, t in LIGNES]
    lots = tok(textes, return_tensors='pt', padding=True)
    sortie = modele.generate(**lots, max_new_tokens=64, num_beams=4)
    traductions = [tok.decode(s, skip_special_tokens=True) for s in sortie]

    segments, t = [], 1.0
    syll_en = syll_fr = 0
    print(f"  {'EN':>3}{'FR':>4}  {'ratio':>6}  original / traduction")
    for (loc, en), fr in zip(LIGNES, traductions):
        n_en = syllabes(en, 'en')
        n_fr = syllabes(fr, 'fr')
        syll_en += n_en
        syll_fr += n_fr
        # Duration available = how long the English line takes to say.
        # Modelled from its syllable count at the English dialogue rate,
        # NOT measured from audio - stated plainly in the write-up.
        duree = n_en / DEBIT_EN
        segments.append({
            'id': f'{len(segments) + 1:03d}',
            'debut': round(t, 3), 'fin': round(t + duree, 3),
            'locuteur': loc, 'voix': 'FR-F-01' if loc == 'ANNA' else 'FR-M-01',
            'original': en, 'traduction': fr})
        t += duree + 0.4
        print(f'  {n_en:>3}{n_fr:>4}  {n_fr / n_en:>6.2f}  {en}')
        print(f'  {"":>3}{"":>4}  {"":>6}  -> {fr}')

    spec = {'langue_source': 'en', 'langue_cible': 'fr',
            'debit': {'fr': DEBIT_FR}, 'tolerance_etirement': 0.06,
            'segments': segments}
    chemin = ICI / 'segments-opusmt.json'
    chemin.write_text(json.dumps(spec, ensure_ascii=False, indent=1),
                      encoding='utf-8')

    print()
    print(f'  syllabes EN {syll_en}  ->  FR {syll_fr}')
    print(f'  expansion mesuree : {syll_fr / syll_en:.3f}  '
          f'({(syll_fr / syll_en - 1) * 100:+.1f} %)')
    print(f'  ecrit : {chemin}')


if __name__ == '__main__':
    main()
