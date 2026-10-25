#!/usr/bin/env python3
# Copyright (C) 2026 SYNERGIELOC
#
# This file is part of "Localisation measurements".
# Licensed under the GNU Affero General Public License v3 or later.
# See the LICENSE file, or <https://www.gnu.org/licenses/>.
"""Did the interpretation keep the words the business cannot afford to lose?

usage: glossaire_terminologie.py glossaire.json transcription.json [--json]

Over an hour, a machine interpreter will render the same term three different
ways. In a technical or financial meeting that is not a style problem: the
listener concludes there are three things. And a figure that arrives altered
is worse than a figure that never arrives, because nobody questions it.

So this checks four things against a glossary you own: the mandated rendering
is used, forbidden renderings are not, the same source term is rendered the
same way all the way through, and **every number in the source appears in the
target**.

Exit 0 if the transcript holds, 1 if findings, 2 on bad input.
Standard library only, no network.
"""
import json
import re
import sys
import unicodedata

NOMBRE = re.compile(r'(?<![\w.,])[-+]?\d[\d   .,]*\d|(?<![\w.,])[-+]?\d')
# Latin letters, so a word boundary means something; otherwise match literally.
A_FRONTIERES = re.compile(r'[a-z]')


class SpecError(ValueError):
    pass


def plier(t):
    """Lower-case and strip accents, so "Provision" and "provisión" match."""
    d = unicodedata.normalize('NFD', (t or '').lower())
    return ''.join(c for c in d if not unicodedata.combining(c))


def present(terme, texte):
    """Word-boundary match for Latin terms, substring match otherwise.

    CJK has no spaces, so a boundary check would never fire there.
    """
    t, x = plier(terme), plier(texte)
    if not t:
        return False
    if A_FRONTIERES.search(t):
        return re.search(r'(?<!\w)' + re.escape(t) + r'(?!\w)', x) is not None
    return t in x


def nombres(texte):
    """Numbers as comparable strings: separators and spacing removed.

    "1 234,50", "1234.50" and "1.234,50" all become "123450" - deliberately,
    because what matters here is that the figure survived, not how it was
    punctuated. A changed digit still shows.
    """
    sortie = []
    for m in NOMBRE.finditer(texte or ''):
        brut = m.group(0)
        chiffres = re.sub(r'[^\d]', '', brut)
        if chiffres:
            sortie.append(chiffres.lstrip('0') or '0')
    return sortie


def evaluer(glossaire, transcription):
    termes = glossaire.get('termes')
    if not isinstance(termes, list) or not termes:
        raise SpecError('"termes" must be a non-empty list of {source, cible}')
    normalises = []
    vus = set()
    for i, t in enumerate(termes, start=1):
        if not isinstance(t, dict):
            raise SpecError(f'termes[{i}] must be an object')
        src = str(t.get('source') or '').strip()
        cible = str(t.get('cible') or '').strip()
        if not src or not cible:
            raise SpecError(f'termes[{i}]: both "source" and "cible" are required')
        if plier(src) in vus:
            raise SpecError(f'termes[{i}]: {src!r} is in the glossary twice')
        vus.add(plier(src))
        interdits = t.get('interdits') or []
        if not isinstance(interdits, list):
            raise SpecError(f'termes[{i}]: "interdits" must be a list')
        normalises.append({'source': src, 'cible': cible,
                           'interdits': [str(x) for x in interdits],
                           'variantes': t.get('variantes') or []})

    segments = transcription.get('segments') if isinstance(transcription, dict) \
        else transcription
    if not isinstance(segments, list) or not segments:
        raise SpecError('the transcript must be a non-empty list of '
                        '{source, cible}, or {"segments": [...]}')

    constats = []
    rendus = {}          # source term -> {rendering: [segment ids]}
    occurrences = 0
    chiffres_perdus = 0

    for i, s in enumerate(segments, start=1):
        if not isinstance(s, dict):
            raise SpecError(f'segment {i} must be an object')
        sid = str(s.get('id') or i)
        src = str(s.get('source') or '')
        cib = str(s.get('cible') or '')
        if not src.strip():
            constats.append(('mineur', sid, 'segment with no source text'))
            continue
        if not cib.strip():
            constats.append(('bloquant', sid,
                             'source present, target empty: the listener got nothing'))
            continue

        for t in normalises:
            if not present(t['source'], src):
                continue
            occurrences += 1
            attendu = present(t['cible'], cib)
            # An accepted variant counts as correct but is recorded, so that
            # three accepted variants still show up as an inconsistency.
            variante = next((v for v in t['variantes'] if present(v, cib)), None)
            interdit = next((x for x in t['interdits'] if present(x, cib)), None)

            if interdit:
                constats.append(('bloquant', sid,
                                 f'"{t["source"]}" rendered as "{interdit}", which the '
                                 f'glossary forbids (expected "{t["cible"]}")'))
                rendus.setdefault(t['source'], {}).setdefault(interdit, []).append(sid)
            elif attendu:
                rendus.setdefault(t['source'], {}).setdefault(t['cible'], []).append(sid)
            elif variante:
                rendus.setdefault(t['source'], {}).setdefault(variante, []).append(sid)
            elif present(t['source'], cib) and plier(t['source']) != plier(t['cible']):
                constats.append(('majeur', sid,
                                 f'"{t["source"]}" left in the source language '
                                 f'(expected "{t["cible"]}")'))
                rendus.setdefault(t['source'], {}).setdefault(
                    f'[untranslated: {t["source"]}]', []).append(sid)
            else:
                constats.append(('majeur', sid,
                                 f'"{t["source"]}" said, but "{t["cible"]}" is not in '
                                 f'the interpretation'))
                rendus.setdefault(t['source'], {}).setdefault('[absent]', []).append(sid)

        # Compare the two multisets both ways. A figure missing on one side and
        # a figure appearing on the other is an ALTERED number, which reads
        # as confident and correct - the worst of the two defects.
        manquants, en_trop = list(nombres(src)), list(nombres(cib))
        for n in list(en_trop):
            if n in manquants:
                manquants.remove(n)
                en_trop.remove(n)
        if manquants and en_trop:
            chiffres_perdus += len(manquants)
            constats.append(('bloquant', sid,
                             f'figure(s) altered: {", ".join(manquants)} said, '
                             f'{", ".join(en_trop)} interpreted. An altered number '
                             f'sounds right and nobody questions it'))
        elif manquants:
            chiffres_perdus += len(manquants)
            constats.append(('bloquant', sid,
                             f'figure(s) {", ".join(manquants)} in the source and not '
                             f'in the interpretation: a dropped number is worse than '
                             f'a dropped sentence'))
        elif en_trop:
            constats.append(('majeur', sid,
                             f'figure(s) {", ".join(en_trop)} in the interpretation and '
                             f'not in the source: invented, or carried over from an '
                             f'earlier segment'))

    # Consistency is judged over the whole meeting, not segment by segment.
    for terme, variantes in sorted(rendus.items()):
        reels = {k: v for k, v in variantes.items() if not k.startswith('[')}
        if len(reels) > 1:
            detail = '; '.join(f'"{k}" ({len(v)}x)' for k, v in sorted(reels.items()))
            constats.append(('majeur', terme,
                             f'rendered {len(reels)} different ways across the meeting '
                             f'- {detail}: the listener hears several things'))

    return {'termes': len(normalises), 'segments': len(segments),
            'occurrences': occurrences, 'chiffres_perdus': chiffres_perdus,
            'rendus': {k: {kk: vv for kk, vv in v.items()}
                       for k, v in sorted(rendus.items())},
            'constats': constats}


def charger(chemin, quoi):
    try:
        with open(chemin, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise SpecError(f'{quoi} unreadable: {e}') from None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if len(args) != 2:
        print('usage: glossaire_terminologie.py glossaire.json transcription.json '
              '[--json]', file=sys.stderr)
        return 2
    try:
        r = evaluer(charger(args[0], 'glossary'), charger(args[1], 'transcript'))
    except SpecError as e:
        print(f'error: {e}', file=sys.stderr)
        return 2

    if '--json' in sys.argv:
        json.dump(r, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        print(f"{r['termes']} glossary term(s), {r['segments']} segment(s), "
              f"{r['occurrences']} occurrence(s) checked")
        if r['chiffres_perdus']:
            print(f"{r['chiffres_perdus']} figure(s) lost")
        print()
        for niveau, ou, msg in r['constats'][:40]:
            print(f'[{niveau:<9}] {ou}: {msg}')
        if len(r['constats']) > 40:
            print(f'... and {len(r["constats"]) - 40} more')
        if not r['constats']:
            print('terminology holds: mandated renderings used, nothing forbidden, '
                  'consistent throughout, every figure carried over.')
    return 1 if r['constats'] else 0


if __name__ == '__main__':
    sys.exit(main())
