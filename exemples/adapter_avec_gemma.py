# Copyright (C) 2026 SYNERGIELOC
#
# This file is part of "Localisation measurements".
# Licensed under the GNU Affero General Public License v3 or later.
# See the LICENSE file, or <https://www.gnu.org/licenses/>.
"""The one step a script cannot do: shorten the line without ruining it.

usage: python exemples/adapter_avec_gemma.py [segments.json] [--modele gemma3:4b]

`ajuster_doublage.py` says *that* a line must lose four syllables. Choosing
which four is writing, and this is where a model earns its place instead of
decorating a pipeline.

Two design points, both learned the hard way on this very example:

**A model cannot count syllables, so it is not asked to.** It is asked for
several variants, from the closest to the original down to the most
elliptical, and the syllable counter picks. Asking a 4B model for "at most
four syllables" produced nothing usable; asking it for six variants and
measuring them produced a line that fits, with the same model.

**The shortest variant is the wrong answer.** Taking it replaces "too long"
with "too short" - the mouth still moving after the line is over - which is a
different defect, not a fix. The acceptable window is `plancher` to
`1 + tolerance`, and inside it the variant closest to filling the time wins.

Gemma runs locally through Ollama. Nothing is accepted because the model
produced it: a rewrite outside the window is reported as outside the window.

Needs Ollama running and the model pulled (`ollama pull gemma3:4b`). Talks to
it with the standard library only.
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ICI = Path(__file__).resolve().parent
sys.path.insert(0, str(ICI.parent / 'localisation'))
from ajuster_doublage import (syllabes, ms, DEBIT_SYLLABES,  # noqa: E402
                              TOLERANCE, PLANCHER)

OLLAMA = 'http://127.0.0.1:11434/api/generate'
MODELE = 'gemma3:4b'
ESSAIS = 3
VARIANTES = 6

CONSIGNE = """Tu adaptes des dialogues pour le doublage.

La replique francaise ci-dessous est TROP LONGUE: elle doit se dire en AU PLUS
{budget} syllabes, et elle en fait {actuel}.

Propose {n} variantes, de la plus proche de l'original a la plus ramassee.
Numerote-les de 1 a {n}, une par ligne, rien d'autre.

Regles:
- garde le sens: ne remplace pas une affirmation par une autre
- dialogue parle, naturel a dire a voix haute; pas de resume
- ne change pas le tutoiement ou le vouvoiement
- les variantes courtes peuvent etre tres elliptiques: trois mots suffisent

Exemple attendu, pour "On devrait y aller maintenant." en 4 syllabes:
1. On devrait y aller.
2. Il faut partir.
3. On y va.
4. Allons-y.

Original anglais: {original}
Replique a raccourcir ({actuel} syllabes): {replique}

Variantes:"""


def score(n, bas, haut, idele):
    """Lower is better. Inside the window, closest to filling the time wins.

    Outside it, a long line is penalised harder than a short one: a rushed
    delivery is heard immediately, a slightly short one reads as a pause.
    """
    if n is None:
        return float('inf')
    if n > haut:
        return 2000.0 + (n - haut)
    if n < bas:
        return 1000.0 + (bas - n)
    return abs(n - idele)


def demander(modele, invite):
    corps = json.dumps({'model': modele, 'prompt': invite, 'stream': False,
                        'options': {'temperature': 0.5, 'num_predict': 200}}
                       ).encode('utf-8')
    req = urllib.request.Request(OLLAMA, data=corps,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read().decode('utf-8')).get('response', '')


def variantes(brut):
    """Pull the numbered variants out of the answer, in the order given."""
    texte = (brut or '').strip().replace('```', '')
    sortie = []
    for ligne in texte.split('\n'):
        ligne = re.sub(r'^\s*\d+\s*[.)\-]\s*', '', ligne.strip())
        ligne = ligne.strip('"“”«»*_ ').strip()
        ligne = re.sub(r'^(?:variantes?|replique reecrite)\s*:\s*', '', ligne,
                       flags=re.I)
        if len(ligne) > 2 and not ligne.lower().startswith(
                ('regle', 'exemple', 'original', 'replique')):
            sortie.append(ligne)
    return sortie


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    modele = MODELE
    if '--modele' in sys.argv:
        i = sys.argv.index('--modele')
        if i + 1 < len(sys.argv):
            modele = sys.argv[i + 1]
            if modele in args:
                args.remove(modele)
    chemin = Path(args[0]) if args else ICI / 'segments-opusmt.json'

    spec = json.loads(chemin.read_text(encoding='utf-8'))
    cible = spec['langue_cible']
    debit = (spec.get('debit') or {}).get(cible) or DEBIT_SYLLABES[cible]
    tol = float(spec.get('tolerance_etirement', TOLERANCE))
    plancher = float(spec.get('plancher', PLANCHER))

    print(f'modele {modele} (local, via Ollama) - debit {debit:g} syll/s')
    print(f'fenetre acceptable {plancher:.2f}x a {1 + tol:.2f}x, '
          f'{VARIANTES} variantes par appel, {ESSAIS} appels au plus\n')

    a_traiter = []
    for s in spec['segments']:
        dispo = ms(s['fin'], 'fin') - ms(s['debut'], 'debut')
        n = syllabes(s['traduction'], cible)
        if (n * 1000.0 / debit) / dispo > 1.0 + tol:
            idele = dispo * debit / 1000.0
            a_traiter.append((s, dispo, n, idele,
                              plancher * idele, (1.0 + tol) * idele))

    if not a_traiter:
        print('  rien a raccourcir.')
        return 0

    print(f'  {len(a_traiter)} ligne(s) rejetee(s) par la mesure\n')
    tenus = 0
    for s, dispo, n, idele, bas, haut in a_traiter:
        print(f'  [{s["id"]}] {dispo} ms disponibles, '
              f'{bas:.1f} a {haut:.1f} syllabes')
        print(f'        avant  ({n:>2} syll) {s["traduction"]}')
        meilleur, meilleur_n, mesurees = None, None, 0
        for _ in range(ESSAIS):
            invite = CONSIGNE.format(budget=int(haut), original=s.get('original', ''),
                                     actuel=n, replique=s['traduction'],
                                     n=VARIANTES)
            try:
                brut = demander(modele, invite)
            except (urllib.error.URLError, OSError, TimeoutError) as e:
                print(f'        ERREUR Ollama: {e}')
                return 2
            for prop in variantes(brut):
                m = syllabes(prop, cible)
                mesurees += 1
                if score(m, bas, haut, idele) < score(meilleur_n, bas, haut, idele):
                    meilleur, meilleur_n = prop, m
            if meilleur_n is not None and bas <= meilleur_n <= haut:
                break

        if meilleur is None:
            print('        apres  (aucune variante exploitable)\n')
            continue
        tient = bas <= meilleur_n <= haut
        tenus += tient
        ratio = (meilleur_n * 1000.0 / debit) / dispo
        verdict = ('TIENT' if tient
                   else 'TOUJOURS TROP LONG' if meilleur_n > haut
                   else 'DESORMAIS TROP COURT')
        print(f'        apres  ({meilleur_n:>2} syll) {meilleur}')
        print(f'        -> {ratio:.2f}x  {verdict}'
              f'  ({mesurees} variantes mesurees)\n')
        s['traduction_adaptee'] = meilleur
        s['adapte_par'] = modele
        s['ratio_apres'] = round(ratio, 3)
        s['tient_apres_adaptation'] = bool(tient)

    sortie = chemin.with_name(chemin.stem + '-adapte.json')
    sortie.write_text(json.dumps(spec, ensure_ascii=False, indent=1),
                      encoding='utf-8')
    print(f'  {tenus}/{len(a_traiter)} dans la fenetre apres adaptation')
    print(f'  ecrit : {sortie.name}')
    print('\n  Propositions d\'un modele, mesurees et non crues. Hors fenetre, '
          'c\'est dit;\n  et le choix final entre des variantes qui tiennent '
          'reste humain.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
