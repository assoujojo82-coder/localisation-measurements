#!/usr/bin/env python3
# Copyright (C) 2026 SYNERGIELOC
#
# This file is part of "Localisation measurements".
# Licensed under the GNU Affero General Public License v3 or later.
# See the LICENSE file, or <https://www.gnu.org/licenses/>.
"""Can this pipeline keep up with a live meeting, and for how long?

usage: budget_latence.py budget.json [--json]

Two numbers decide whether live interpretation is usable, and only one of
them gets measured.

The first is latency: how far behind the speaker the listener is. Past about
three seconds a listener can no longer tie an answer to its question.

The second is drift, and it is the one that kills long meetings. If the
translated speech takes longer to say than the original, every sentence adds
to the gap. A pipeline that sits two seconds behind at minute one can sit
forty seconds behind at minute thirty, and nobody notices during a five-minute
demo.

This computes both from stage figures you measure, and says which stage to cut
and whether the design holds for an hour.

Exit 0 if latency and drift both hold, 1 if findings, 2 on bad input.
Standard library only, no network.
"""
import json
import math
import sys

CIBLE_MS = 3000          # a listener loses the thread past roughly this
CHUNK_CONFORTABLE = 500  # an audio chunk longer than this cannot be made up later
# Stages that must be present, or the budget is describing something else.
ATTENDUES = ('asr', 'mt', 'tts')


class SpecError(ValueError):
    pass


def nombre(v, ou, defaut=None):
    if v is None and defaut is not None:
        return float(defaut)
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise SpecError(f'{ou}: {v!r} is not a number') from None
    if x < 0:
        raise SpecError(f'{ou}: {x} is negative')
    return x


def evaluer(spec):
    cible = nombre(spec.get('cible_ms'), 'cible_ms', CIBLE_MS)
    if cible <= 0:
        raise SpecError('cible_ms must be positive')

    etapes = spec.get('etapes')
    if not isinstance(etapes, list) or not etapes:
        raise SpecError('"etapes" must be a non-empty list of '
                        '{nom, p50, p95}')

    constats, lignes = [], []
    somme50 = somme95 = 0.0
    variance = 0.0
    noms = []
    for i, e in enumerate(etapes, start=1):
        nom = str(e.get('nom') or f'etape{i}').strip()
        if nom in noms:
            constats.append(('majeur', nom, 'stage name used twice'))
        noms.append(nom)
        p50 = nombre(e.get('p50'), f'{nom}.p50')
        p95 = nombre(e.get('p95'), f'{nom}.p95', p50)
        if p95 < p50:
            raise SpecError(f'{nom}: p95 ({p95}) is below p50 ({p50})')
        somme50 += p50
        somme95 += p95
        # Spread above the median, kept squared for the independent estimate.
        variance += (p95 - p50) ** 2
        lignes.append({'nom': nom, 'p50': p50, 'p95': p95,
                       'part_p50': 0.0})

    for l in lignes:
        l['part_p50'] = round(100.0 * l['p50'] / somme50, 1) if somme50 else 0.0

    # Summing p95 is the worst case: it assumes every stage has its bad day at
    # the same moment. If the stages are independent, the real p95 sits near
    # the median plus the combined spread. Report both and design on the
    # pessimistic one only if the stages actually share a cause.
    p95_independant = somme50 + math.sqrt(variance)

    manquantes = [n for n in ATTENDUES
                  if not any(n in l['nom'].lower() for l in lignes)]
    if manquantes:
        constats.append(('majeur', 'etapes',
                         f'no stage looks like {", ".join(manquantes)}: '
                         f'a budget missing a stage always holds'))

    chunk = next((l for l in lignes if 'chunk' in l['nom'].lower()), None)
    if chunk and chunk['p50'] > CHUNK_CONFORTABLE:
        constats.append(('majeur', chunk['nom'],
                         f"{chunk['p50']:.0f} ms of audio per chunk: this latency is "
                         f"structural, no later stage can give it back"))

    if somme50 > cible:
        pire = max(lignes, key=lambda l: l['p50'])
        constats.append(('bloquant', 'latence',
                         f'median end-to-end {somme50:.0f} ms over the {cible:.0f} ms '
                         f'target: cut {somme50 - cible:.0f} ms, starting with '
                         f'"{pire["nom"]}" ({pire["p50"]:.0f} ms, '
                         f'{pire["part_p50"]:.0f}% of the budget)'))
    elif p95_independant > cible:
        constats.append(('majeur', 'latence',
                         f'median {somme50:.0f} ms holds but the p95 estimate '
                         f'{p95_independant:.0f} ms does not: one listener in twenty '
                         f'loses the thread'))

    # Drift: the part a five-minute demo never shows.
    derive = None
    d = spec.get('derive')
    if isinstance(d, dict):
        expansion = nombre(d.get('expansion'), 'derive.expansion', 1.0)
        debit_src = nombre(d.get('debit_source'), 'derive.debit_source')
        debit_tts = nombre(d.get('debit_tts'), 'derive.debit_tts')
        part_parlee = nombre(d.get('part_parlee'), 'derive.part_parlee', 0.6)
        if debit_src <= 0 or debit_tts <= 0:
            raise SpecError('derive.debit_source and derive.debit_tts must be positive')
        if not 0 < part_parlee <= 1:
            raise SpecError('derive.part_parlee must be above 0 and at most 1')

        # Per second of actual speech: the source emits debit_src units, the
        # target needs expansion times as many, delivered at debit_tts.
        secondes_cible = expansion * debit_src / debit_tts
        derive_par_s_parlee = secondes_cible - 1.0
        # A meeting is not wall-to-wall speech; silence is where you catch up.
        derive_par_minute = derive_par_s_parlee * part_parlee * 60.0
        acceptable = derive_par_minute <= 0.0
        # What the synthesis would have to deliver to break even.
        debit_requis = expansion * debit_src
        derive = {'expansion': expansion, 'debit_source': debit_src,
                  'debit_tts': debit_tts, 'part_parlee': part_parlee,
                  'derive_s_par_minute': round(derive_par_minute, 2),
                  'derive_s_sur_30min': round(derive_par_minute * 30, 1),
                  'debit_tts_requis': round(debit_requis, 2),
                  'tient': acceptable}
        if derive_par_minute > 0:
            constats.append(('bloquant', 'derive',
                             f'the gap grows {derive_par_minute:.2f} s per minute '
                             f'({derive_par_minute * 30:.0f} s after half an hour): '
                             f'synthesis must deliver {debit_requis:.2f} units/s, '
                             f'not {debit_tts:.2f} - speed it up, compress the '
                             f'translation, or drop to summary mode'))
        elif derive_par_minute > -0.05 * 60:
            constats.append(('mineur', 'derive',
                             f'break-even at {derive_par_minute:.2f} s per minute: '
                             f'no margin for a fast speaker'))
    else:
        constats.append(('majeur', 'derive',
                         'no "derive" block: latency alone says nothing about '
                         'whether the pipeline survives an hour'))

    return {'cible_ms': cible, 'p50_total': round(somme50, 1),
            'p95_borne_haute': round(somme95, 1),
            'p95_estime_independant': round(p95_independant, 1),
            'etapes': lignes, 'derive': derive, 'constats': constats}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 1:
        print('usage: budget_latence.py budget.json [--json]', file=sys.stderr)
        return 2
    try:
        with open(args[0], encoding='utf-8') as f:
            spec = json.load(f)
        r = evaluer(spec)
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
        print(f"target {r['cible_ms']:.0f} ms end to end")
        print()
        print(f"  {'stage':<18}{'p50':>8}{'p95':>8}{'share':>8}")
        for l in r['etapes']:
            print(f"  {l['nom'][:17]:<18}{l['p50']:>8.0f}{l['p95']:>8.0f}"
                  f"{l['part_p50']:>7.0f}%")
        print(f"  {'-' * 42}")
        print(f"  {'median total':<18}{r['p50_total']:>8.0f}")
        print(f"  {'p95 (independent)':<18}{r['p95_estime_independant']:>8.0f}")
        print(f"  {'p95 (worst case)':<18}{r['p95_borne_haute']:>8.0f}")
        if r['derive']:
            d = r['derive']
            print()
            print(f"  drift {d['derive_s_par_minute']:+.2f} s per minute, "
                  f"{d['derive_s_sur_30min']:+.0f} s over half an hour "
                  f"({'holds' if d['tient'] else 'does not hold'})")
        print()
        for niveau, ou, msg in r['constats']:
            print(f'[{niveau:<9}] {ou}: {msg}')
        if not r['constats']:
            print('latency and drift both hold on the figures given.')
        print()
        print('Computed from the figures supplied. Measure them on your own '
              'hardware under load, not from a vendor page.')
    return 1 if r['constats'] else 0


if __name__ == '__main__':
    sys.exit(main())
