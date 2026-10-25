#!/usr/bin/env python3
# Copyright (C) 2026 SYNERGIELOC
#
# This file is part of "Localisation measurements".
# Licensed under the GNU Affero General Public License v3 or later.
# See the LICENSE file, or <https://www.gnu.org/licenses/>.
"""Will the translated line fit in the mouth it has to come out of?

usage: ajuster_doublage.py segments.json [--modele syllabes|caracteres] [--json]

This is the defect that ruins a dub: the translation is correct, and it is
twenty per cent too long. In the studio that becomes a rushed delivery, a
line that runs under the next shot, or a time-stretch everybody can hear.
It is cheap to find here and expensive to find at the mix.

The script estimates how long each translated line takes to speak and
compares it with the time available, then says what a human must rewrite and
by how much. It does not rewrite anything: adaptation is a craft, and a
machine that shortens a line on its own produces dialogue nobody would say.

Exit 0 if every line fits, 1 if findings, 2 on bad input.
Standard library only, no network. Durations are integer milliseconds.
"""
import json
import sys
import unicodedata

# Speaking rate in syllables per second, dialogue at a natural pace. These are
# starting points: MEASURE YOUR OWN TALENT on twenty real lines and put the
# result in "debit". A rate that is wrong by 10% moves every verdict.
DEBIT_SYLLABES = {'fr': 5.3, 'en': 5.6, 'es': 6.1, 'de': 5.1, 'it': 5.8,
                  'pt': 5.9, 'nl': 5.2, 'ja': 7.3, 'zh': 5.2, 'ar': 5.0,
                  'ru': 5.3, 'pl': 5.4, 'tr': 5.3, 'ko': 6.2}
# Characters per second, for scripts where counting syllables makes no sense.
DEBIT_CARACTERES = {'fr': 14.0, 'en': 14.5, 'es': 15.0, 'de': 13.5, 'it': 14.5,
                    'pt': 14.5, 'nl': 13.5, 'ja': 7.5, 'zh': 5.5, 'ar': 12.0,
                    'ru': 13.0, 'pl': 13.0, 'tr': 13.5, 'ko': 8.0}
VOYELLES = set('aeiouyàâäáãåèéêëìíîïòóôöõùúûüÿœæ')
# A time-stretch under this is inaudible on dialogue; past it, the voice is
# recognisably processed. 6% is the usual studio ceiling.
TOLERANCE = 0.06
# Under this ratio the mouth is still moving when the line is over.
PLANCHER = 0.80


class SpecError(ValueError):
    pass


def syllabes(texte, langue):
    """Count vowel groups, then correct the commonest systematic error.

    This is an estimate, not a phonetiser. It is within about one syllable
    per line on Latin scripts, which is enough to catch a line that is 20%
    too long - and not enough to arbitrate a line that is 2% too long.
    """
    nu = ''.join(c for c in unicodedata.normalize('NFC', texte.lower())
                 if c.isalpha() or c.isspace() or c == "'")
    total = 0
    for mot in nu.split():
        groupes, dedans = 0, False
        for c in mot:
            if c in VOYELLES:
                if not dedans:
                    groupes += 1
                dedans = True
            else:
                dedans = False
        # French drops a final unstressed "e" in speech: "parle" is one
        # syllable, not two. Keep at least one syllable per word.
        if langue.startswith('fr') and len(mot) > 2 and mot.endswith('e') \
                and mot[-2] not in VOYELLES:
            groupes -= 1
        total += max(1, groupes) if mot else 0
    return total


def unites(texte, langue, modele):
    if modele == 'caracteres':
        return len(''.join(texte.split())), 'char'
    return syllabes(texte, langue), 'syll'


def ms(v, ou):
    """Accept seconds as a number, or HH:MM:SS,mmm / MM:SS.mmm as a string."""
    if isinstance(v, (int, float)):
        return int(round(float(v) * 1000))
    if isinstance(v, str) and ':' in v:
        morceaux = v.replace(',', '.').split(':')
        if len(morceaux) > 3:
            raise SpecError(f'{ou}: {v!r} is not a timecode')
        try:
            total = 0.0
            for m in morceaux:
                total = total * 60 + float(m)
        except ValueError:
            raise SpecError(f'{ou}: {v!r} is not a timecode') from None
        return int(round(total * 1000))
    raise SpecError(f'{ou}: expected seconds or HH:MM:SS,mmm, got {v!r}')


def evaluer(spec, modele):
    cible = str(spec.get('langue_cible') or '').lower()
    if not cible:
        raise SpecError('"langue_cible" is required: the rate depends on it')
    source = str(spec.get('langue_source') or '').lower()
    table = DEBIT_CARACTERES if modele == 'caracteres' else DEBIT_SYLLABES
    debits = dict(table)
    debits.update({str(k).lower(): float(v)
                   for k, v in (spec.get('debit') or {}).items()})
    if cible not in debits:
        raise SpecError(f'no speaking rate for {cible!r}: add it to "debit"')
    debit = debits[cible]
    if debit <= 0:
        raise SpecError(f'the rate for {cible!r} must be positive')
    # "measured" means the caller supplied a rate for THIS language, not that a
    # default happened to exist. The distinction is printed, because a verdict
    # built on a default rate is a guess with two decimals.
    mesure = cible in (spec.get('debit') or {})
    tolerance = float(spec.get('tolerance_etirement', TOLERANCE))
    plancher = float(spec.get('plancher', PLANCHER))

    segments = spec.get('segments')
    if not isinstance(segments, list) or not segments:
        raise SpecError('"segments" must be a non-empty list')

    constats, lignes = [], []
    voix_par_locuteur, locuteurs_par_voix = {}, {}
    par_locuteur = {}
    ids = set()
    a_recuperer = 0

    for i, s in enumerate(segments, start=1):
        sid = str(s.get('id') or i)
        if sid in ids:
            constats.append(('majeur', sid, 'segment id used twice'))
        ids.add(sid)

        debut, fin = ms(s.get('debut'), f'{sid}.debut'), ms(s.get('fin'), f'{sid}.fin')
        if fin <= debut:
            constats.append(('bloquant', sid,
                             f'ends before it starts: {debut} -> {fin} ms'))
            continue
        dispo = fin - debut

        traduction = (s.get('traduction') or '').strip()
        if not traduction:
            constats.append(('bloquant', sid, 'no translation: nothing to record'))
            continue

        locuteur = str(s.get('locuteur') or '').strip() or '(unnamed)'
        voix = str(s.get('voix') or '').strip()
        if voix:
            voix_par_locuteur.setdefault(locuteur, set()).add(voix)
            locuteurs_par_voix.setdefault(voix, set()).add(locuteur)
        par_locuteur.setdefault(locuteur, []).append((debut, fin, sid))

        n, unite = unites(traduction, cible, modele)
        estime = int(round(n * 1000.0 / debit))
        ratio = estime / float(dispo)

        if ratio > 1.0 + tolerance:
            # How much must go, expressed in the unit the adapter works in.
            garder = int(dispo * (1.0 + tolerance) * debit / 1000.0)
            a_couper = max(1, n - garder)
            manque = estime - int(dispo * (1.0 + tolerance))
            a_recuperer += manque
            constats.append(('bloquant', sid,
                             f'{ratio:.2f}x too long for the time available '
                             f'({estime} ms of speech in {dispo} ms): cut about '
                             f'{a_couper} {unite}, or {manque} ms'))
            etat = 'a_raccourcir'
        elif ratio > 1.0:
            constats.append(('mineur', sid,
                             f'{ratio:.2f}x: fits only with a '
                             f'{(ratio - 1.0) * 100:.1f}% time-stretch, '
                             f'under the {tolerance * 100:.0f}% ceiling'))
            etat = 'etirement'
        elif ratio < plancher:
            constats.append(('majeur', sid,
                             f'{ratio:.2f}x: only {estime} ms of speech for '
                             f'{dispo} ms of moving lips - the mouth keeps going '
                             f'after the line ends'))
            etat = 'trop_court'
        else:
            etat = 'tient'

        source_n = None
        if source and (s.get('original') or '').strip():
            source_n, _ = unites(s['original'].strip(), source, modele)

        lignes.append({'id': sid, 'locuteur': locuteur, 'voix': voix or None,
                       'dispo_ms': dispo, 'estime_ms': estime,
                       'ratio': round(ratio, 3), 'unites': n, 'unite': unite,
                       'unites_source': source_n, 'etat': etat})

    # One mouth cannot say two things at once.
    for locuteur, bornes in par_locuteur.items():
        bornes.sort()
        for (d1, f1, i1), (d2, f2, i2) in zip(bornes, bornes[1:]):
            if d2 < f1:
                constats.append(('bloquant', f'{i1}/{i2}',
                                 f'{locuteur} speaks in two segments that overlap by '
                                 f'{f1 - d2} ms: one mouth, two lines'))

    for locuteur, v in sorted(voix_par_locuteur.items()):
        if len(v) > 1:
            constats.append(('bloquant', locuteur,
                             f'cast to {len(v)} different voices '
                             f'({", ".join(sorted(v))}): the character changes voice'))
    for voix, l in sorted(locuteurs_par_voix.items()):
        if len(l) > 1:
            constats.append(('majeur', voix,
                             f'one voice for {len(l)} characters '
                             f'({", ".join(sorted(l))}): they will be confused'))

    compte = {}
    for l in lignes:
        compte[l['etat']] = compte.get(l['etat'], 0) + 1

    return {'langue_cible': cible, 'modele': modele,
            'debit': debit, 'debit_mesure': bool(mesure),
            'tolerance_etirement': tolerance, 'plancher': plancher,
            'segments': len(segments), 'evalues': len(lignes),
            'repartition': compte, 'a_recuperer_ms': a_recuperer,
            'lignes': lignes, 'constats': constats}


def main():
    # --modele takes a value: skip it, or it is counted as the segments file.
    args, modele, saute = [], 'syllabes', False
    for x in sys.argv[1:]:
        if saute:
            if x not in ('syllabes', 'caracteres'):
                print('error: --modele expects syllabes or caracteres', file=sys.stderr)
                return 2
            modele, saute = x, False
            continue
        if x == '--modele':
            saute = True
            continue
        if not x.startswith('--'):
            args.append(x)
    if saute:
        print('error: --modele expects syllabes or caracteres', file=sys.stderr)
        return 2
    if len(args) != 1:
        print('usage: ajuster_doublage.py segments.json '
              '[--modele syllabes|caracteres] [--json]', file=sys.stderr)
        return 2

    try:
        with open(args[0], encoding='utf-8') as f:
            spec = json.load(f)
        r = evaluer(spec, modele)
    except (OSError, json.JSONDecodeError) as e:
        print(f'error: {e}', file=sys.stderr)
        return 2
    except SpecError as e:
        print(f'error: {e}', file=sys.stderr)
        return 2

    if '--json' in sys.argv:
        json.dump(r, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        mesure = 'measured' if r['debit_mesure'] else 'DEFAULT - calibrate it'
        print(f"target {r['langue_cible']}, {r['modele']} model, "
              f"rate {r['debit']:g} {'char' if r['modele'] == 'caracteres' else 'syll'}/s "
              f"({mesure})")
        print(f"{r['evalues']} line(s) evaluated of {r['segments']}")
        print()
        print(f"  {'id':<6}{'speaker':<12}{'avail':>8}{'spoken':>8}{'ratio':>7}  state")
        for l in r['lignes'][:40]:
            print(f"  {l['id']:<6}{l['locuteur'][:11]:<12}{l['dispo_ms']:>8}"
                  f"{l['estime_ms']:>8}{l['ratio']:>7.2f}  {l['etat']}")
        if len(r['lignes']) > 40:
            print(f"  ... and {len(r['lignes']) - 40} more")
        print()
        for etat in ('tient', 'etirement', 'trop_court', 'a_raccourcir'):
            if etat in r['repartition']:
                print(f"  {etat:<14}{r['repartition'][etat]}")
        if r['a_recuperer_ms']:
            print(f"\n  {r['a_recuperer_ms']} ms to recover in all, by rewriting.")
        print()
        for niveau, ou, msg in r['constats'][:40]:
            print(f'[{niveau:<9}] {ou}: {msg}')
        if len(r['constats']) > 40:
            print(f'... and {len(r["constats"]) - 40} more')
        if not r['constats']:
            print('every line fits: timing, speaker overlap and casting all hold.')
        print()
        print('Estimated speech durations, to be confirmed in the booth. '
              'The script proposes what to rewrite; the adaptation is a human craft.')
    return 1 if r['constats'] else 0


if __name__ == '__main__':
    sys.exit(main())
