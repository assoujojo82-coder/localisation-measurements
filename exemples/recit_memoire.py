# Copyright (C) 2026 SYNERGIELOC
#
# This file is part of "Localisation measurements".
# Licensed under the GNU Affero General Public License v3 or later.
# See the LICENSE file, or <https://www.gnu.org/licenses/>.
"""Make a recording understandable, and name what the machine quietly lost.

usage: python exemples/recit_memoire.py captions.srt [--langue fr] [--json]

Someone recorded a grandparent. The captions exist, the language does not.
Upload it to a service and you have handed a dead person's voice to a vendor;
run it here and nothing leaves the machine.

The translation is the easy half. The hard half is that a machine translation
is **fluent when it is wrong**: a clause goes missing and what remains reads
perfectly, so nobody ever questions it. That is the thing worth catching when
the recording cannot be made again.

So this produces a bilingual record AND a list of the lines where something
was probably lost - measured, not guessed:

- a figure in the source that is absent from the translation (a date, an age,
  a year - exactly what a family record is made of);
- a line whose translation is far shorter than the original, which is how a
  dropped clause looks from the outside;
- cue timing that does not hold, so the record stays in step with the audio.

Needs torch + transformers, and about 300 MB of Opus-MT on first run. The
translation model is Apache-2.0 and runs locally.
"""
import json
import re
import sys
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent / 'localisation'))
from valider_sous_titres import analyser, lire, decouper, TC_SRT, TC_VTT, ms  # noqa: E402
from ajuster_doublage import syllabes  # noqa: E402
from glossaire_terminologie import nombres  # noqa: E402

MODELES = {'fr': 'Helsinki-NLP/opus-mt-en-fr', 'es': 'Helsinki-NLP/opus-mt-en-es',
           'de': 'Helsinki-NLP/opus-mt-en-de', 'it': 'Helsinki-NLP/opus-mt-en-it'}
# Sous ce rapport de syllabes, une traduction fluide cache le plus souvent une
# proposition disparue. Mesuré sur Opus-MT : la ligne « They made their choice.
# We make ours. » est revenue à 0,50x, la seconde phrase effacée.
PLANCHER_PERTE = 0.60


def cues(chemin):
    """Les répliques, dans l'ordre, avec leur timecode."""
    texte, _ = lire(chemin)
    sortie = []
    for depart, bloc in decouper(texte):
        if bloc[0].strip().upper().startswith(('WEBVTT', 'NOTE', 'STYLE', 'REGION')):
            continue
        i = next((k for k, l in enumerate(bloc) if '-->' in l), None)
        if i is None:
            continue
        m = TC_SRT.match(bloc[i].strip()) or TC_VTT.match(bloc[i].strip())
        if not m:
            continue
        g = m.groups()
        corps = ' '.join(l.strip() for l in bloc[i + 1:] if l.strip())
        corps = re.sub(r'</?[^>]+>', '', corps).strip()
        if corps:
            sortie.append({'debut': ms(*g[:4]), 'fin': ms(*g[4:]),
                           'ligne': depart, 'source': corps})
    return sortie


def horodatage(millis):
    s, ms_ = divmod(int(millis), 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f'{h:02d}:{m:02d}:{s:02d},{ms_:03d}'


def traduire(textes, langue):
    from transformers import MarianMTModel, MarianTokenizer
    nom = MODELES[langue]
    print(f'  chargement de {nom} (Apache-2.0, local)...', flush=True)
    tok = MarianTokenizer.from_pretrained(nom)
    modele = MarianMTModel.from_pretrained(nom)
    sortie = []
    for debut in range(0, len(textes), 16):
        lot = textes[debut:debut + 16]
        enc = tok(lot, return_tensors='pt', padding=True, truncation=True, max_length=512)
        gen = modele.generate(**enc, max_new_tokens=256, num_beams=4)
        sortie += [tok.decode(x, skip_special_tokens=True) for x in gen]
        print(f'    {len(sortie)}/{len(textes)}', flush=True)
    return sortie


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    langue = 'fr'
    if '--langue' in sys.argv:
        i = sys.argv.index('--langue')
        if i + 1 < len(sys.argv):
            langue = sys.argv[i + 1]
            if langue in args:
                args.remove(langue)
    if len(args) != 1:
        print('usage: recit_memoire.py captions.srt [--langue fr] [--json]',
              file=sys.stderr)
        return 2
    if langue not in MODELES:
        print(f'error: pas de modèle local pour {langue!r} '
              f'({", ".join(sorted(MODELES))})', file=sys.stderr)
        return 2

    chemin = Path(args[0])
    try:
        # La limite de vitesse de lecture depend de la langue : juger des
        # sous-titres anglais avec la limite par defaut (17) invente un defaut.
        timing = analyser(str(chemin), 'en')
        repliques = cues(str(chemin))
    except (OSError, ValueError) as e:
        print(f'error: {e}', file=sys.stderr)
        return 2
    if not repliques:
        print('error: aucune réplique lisible dans ce fichier', file=sys.stderr)
        return 2

    print(f'  {len(repliques)} réplique(s), {timing["duree_dialogue_ms"] / 1000:.0f} s '
          f'de parole, encodage {timing["encodage"]}')
    traductions = traduire([r['source'] for r in repliques], langue)

    pertes = []
    for r, t in zip(repliques, traductions):
        r['cible'] = t
        manquants = list(nombres(r['source']))
        for n in nombres(t):
            if n in manquants:
                manquants.remove(n)
        n_src = syllabes(r['source'], 'en') or 1
        ratio = syllabes(t, langue) / n_src
        r['ratio'] = round(ratio, 2)
        motifs = []
        if manquants:
            motifs.append('chiffre(s) absent(s) de la traduction : '
                          + ', '.join(manquants))
        if ratio < PLANCHER_PERTE:
            motifs.append(f'traduction {ratio:.2f}x plus courte que l’original : '
                          f'une proposition a probablement disparu')
        if motifs:
            r['motifs'] = motifs
            pertes.append(r)

    if '--json' in sys.argv:
        json.dump({'repliques': repliques, 'pertes': len(pertes),
                   'timing': timing['constats']},
                  sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 1 if pertes or timing['constats'] else 0

    sortie = chemin.with_name(chemin.stem + f'-{langue}.md')
    lignes = [f'# {chemin.stem}', '',
              f'Récit bilingue, {len(repliques)} répliques. Traduction locale '
              f'({MODELES[langue]}, Apache-2.0).', '',
              '> Traduction automatique, relue par personne. Les passages signalés '
              'plus bas sont ceux où la machine a probablement perdu quelque chose.',
              '']
    for r in repliques:
        marque = '  ⚠' if r.get('motifs') else ''
        lignes += [f'**{horodatage(r["debut"])}**{marque}', '',
                   f'> {r["source"]}', '', r['cible'], '']
    sortie.write_text('\n'.join(lignes), encoding='utf-8')

    print(f'\n  récit écrit : {sortie.name}')
    print(f'\n  {len(pertes)} réplique(s) où quelque chose a probablement été perdu')
    for r in pertes[:12]:
        print(f'\n  {horodatage(r["debut"])}  (ratio {r["ratio"]})')
        print(f'    source : {r["source"][:88]}')
        print(f'    rendu  : {r["cible"][:88]}')
        for m in r['motifs']:
            print(f'    -> {m}')
    if timing['constats']:
        print(f'\n  {len(timing["constats"])} défaut(s) de minutage '
              f'(le récit se décale de l’audio) :')
        for niveau, ou, msg in timing['constats'][:5]:
            print(f'    [{niveau}] {ou}: {msg}')
    if not pertes and not timing['constats']:
        print('  rien de signalé : les chiffres sont tous passés, aucune réplique '
              'anormalement courte, le minutage tient.')
    print('\n  Rien n’a quitté cette machine.')
    return 1 if pertes or timing['constats'] else 0


if __name__ == '__main__':
    sys.exit(main())
