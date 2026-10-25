#!/usr/bin/env python3
# Copyright (C) 2026 SYNERGIELOC
#
# This file is part of "Localisation measurements".
# Licensed under the GNU Affero General Public License v3 or later.
# See the LICENSE file, or <https://www.gnu.org/licenses/>.
"""Check a subtitle file the way a broadcaster will, before anyone watches it.

usage: valider_sous_titres.py fichier.srt [--langue fr] [--fps 25]
                              [--duree 5400.0] [--json]

A subtitle file that plays fine in VLC is still sent back when two cues
overlap, a line runs past 42 characters, or the reading speed is above what a
viewer can follow. Those defects are invisible on a laptop and obvious on a
delivery report.

This reads the file and writes nothing. Timecodes are handled as integer
milliseconds, never as floats: a rounding error of one frame is a defect.

Exit 0 if conformant, 1 if findings, 2 if unreadable.
Standard library only, no network.
"""
import argparse
import json
import re
import sys

# Reading speed in characters per second. Latin scripts are read at a similar
# rate; CJK is counted in characters, so its limit is far lower. These are the
# usual house limits, not a law - override them per client.
CPS = {'fr': 17.0, 'en': 20.0, 'es': 17.0, 'de': 16.0, 'it': 17.0,
       'pt': 17.0, 'nl': 16.0, 'ar': 16.0, 'ja': 7.0, 'zh': 7.0, 'ko': 9.0}
CPS_DEFAUT = 17.0
LIGNE_MAX = 42          # characters per line
LIGNES_MAX = 2          # lines per cue
DUREE_MIN_MS = 1000     # a cue shorter than a second cannot be read
DUREE_MAX_MS = 7000     # a cue longer than seven seconds is re-read
# Two touching cues flicker: leave at least two frames of black between them.
ECART_MIN_FRAMES = 2

TC_SRT = re.compile(r'^(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*'
                    r'(\d{2}):(\d{2}):(\d{2})[,.](\d{3})')
TC_VTT = re.compile(r'^(?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*'
                    r'(?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3})')
BALISE = re.compile(r'</?(?:i|b|u|font|v|c|ruby|rt)\b[^>]*>', re.I)
# A cue that is only a sound description is not dialogue and is not read aloud.
NON_DIALOGUE = re.compile(r'^\s*[\[(].*[\])]\s*$|^\s*[A-ZÀ-Þ \-]{2,}:\s*$')


def lire(chemin):
    """Subtitles arrive as UTF-8, UTF-8 with a BOM, or Windows-1252."""
    brut = open(chemin, 'rb').read()
    if brut.startswith(b'\xef\xbb\xbf'):
        return brut[3:].decode('utf-8'), 'UTF-8 with BOM'
    for enc in ('utf-8', 'cp1252', 'iso-8859-15'):
        try:
            return brut.decode(enc), enc
        except UnicodeDecodeError:
            continue
    raise ValueError('file is in none of UTF-8, CP1252 or ISO-8859-15')


def ms(h, m, s, milli):
    return ((int(h or 0) * 60 + int(m)) * 60 + int(s)) * 1000 + int(milli)


def decouper(texte):
    """Split into cues on blank lines, keeping the source line number."""
    lignes = texte.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    blocs, courant, depart = [], [], 1
    for n, l in enumerate(lignes, start=1):
        if l.strip() == '':
            if courant:
                blocs.append((depart, courant))
                courant = []
        else:
            if not courant:
                depart = n
            courant.append(l)
    if courant:
        blocs.append((depart, courant))
    return blocs


def analyser(chemin, langue=None, fps=25.0, duree_media=None):
    texte, encodage = lire(chemin)
    if not texte.strip():
        raise ValueError('empty file')
    vtt = texte.lstrip().upper().startswith('WEBVTT')
    cps_max = CPS.get((langue or '').lower(), CPS_DEFAUT)
    ecart_min = int(round(ECART_MIN_FRAMES * 1000.0 / fps))

    constats, cues = [], []
    numeros = {}
    for depart, bloc in decouper(texte):
        if vtt and bloc[0].strip().upper().startswith(('WEBVTT', 'NOTE', 'STYLE', 'REGION')):
            continue

        # The timecode is the first line that looks like one; what precedes it
        # is the cue number (SRT) or an identifier (VTT).
        i_tc = next((i for i, l in enumerate(bloc) if '-->' in l), None)
        if i_tc is None:
            constats.append(('majeur', f'ligne {depart}',
                             'block with no timecode: stray text or a missing blank line'))
            continue

        ligne_tc = bloc[i_tc]
        m = TC_SRT.match(ligne_tc.strip()) or TC_VTT.match(ligne_tc.strip())
        if not m:
            constats.append(('bloquant', f'ligne {depart + i_tc}',
                             f'unreadable timecode {ligne_tc.strip()[:40]!r}: '
                             f'expected HH:MM:SS,mmm --> HH:MM:SS,mmm'))
            continue
        g = m.groups()
        debut, fin = ms(*g[:4]), ms(*g[4:])

        if i_tc == 1:
            brut_num = bloc[0].strip()
            if brut_num.isdigit():
                numeros.setdefault(int(brut_num), []).append(depart)

        corps = [l for l in bloc[i_tc + 1:]]
        texte_cue = '\n'.join(corps).strip()
        nu = BALISE.sub('', texte_cue)
        ou = f'cue a {ligne_tc.strip()[:12]}'

        if not texte_cue:
            constats.append(('bloquant', ou, 'cue with a timecode and no text'))
        if fin <= debut:
            constats.append(('bloquant', ou,
                             f'ends before it starts (or lasts 0 ms): '
                             f'{debut} -> {fin} ms'))
            cues.append({'debut': debut, 'fin': fin, 'texte': nu, 'ligne': depart})
            continue

        duree = fin - debut
        if duree < DUREE_MIN_MS:
            constats.append(('majeur', ou,
                             f'lasts {duree} ms: under {DUREE_MIN_MS} ms nothing is read'))
        if duree > DUREE_MAX_MS:
            constats.append(('mineur', ou,
                             f'lasts {duree} ms: over {DUREE_MAX_MS} ms the viewer re-reads it'))

        # Reading speed is the check that most often comes back from QC.
        caracteres = len(nu.replace('\n', ' '))
        if caracteres and not NON_DIALOGUE.match(nu):
            cps = caracteres * 1000.0 / duree
            if cps > cps_max:
                besoin = int(round(caracteres * 1000.0 / cps_max)) - duree
                constats.append(('majeur', ou,
                                 f'reading speed {cps:.1f} char/s above {cps_max:.0f} '
                                 f'for {langue or "default"}: needs {besoin} ms more, '
                                 f'or {caracteres - int(duree * cps_max / 1000.0)} fewer characters'))

        for j, l in enumerate(corps, start=1):
            propre = BALISE.sub('', l)
            if len(propre) > LIGNE_MAX:
                constats.append(('majeur', ou,
                                 f'line {j} is {len(propre)} characters, over {LIGNE_MAX}'))
            if propre != propre.strip():
                constats.append(('mineur', ou, f'line {j} has leading or trailing spaces'))
        if len(corps) > LIGNES_MAX:
            constats.append(('majeur', ou,
                             f'{len(corps)} lines, over {LIGNES_MAX}: the image is covered'))

        if duree_media is not None and fin > int(duree_media * 1000):
            constats.append(('bloquant', ou,
                             f'ends at {fin} ms, past the {int(duree_media * 1000)} ms '
                             f'of media given'))

        cues.append({'debut': debut, 'fin': fin, 'texte': nu, 'ligne': depart})

    # Order, overlap and gap are judged on the sequence, not on one cue.
    for a, b in zip(cues, cues[1:]):
        if b['debut'] < a['debut']:
            constats.append(('bloquant', f'ligne {b["ligne"]}',
                             'cue starts before the previous one: the file is out of order'))
        elif b['debut'] < a['fin']:
            constats.append(('bloquant', f'ligne {b["ligne"]}',
                             f'overlaps the previous cue by {a["fin"] - b["debut"]} ms'))
        elif b['debut'] - a['fin'] < ecart_min:
            constats.append(('mineur', f'ligne {b["ligne"]}',
                             f'only {b["debut"] - a["fin"]} ms after the previous cue '
                             f'(under {ecart_min} ms = {ECART_MIN_FRAMES} frames at {fps:g} fps): '
                             f'the two flicker into one'))

    for num, lignes_num in sorted(numeros.items()):
        if len(lignes_num) > 1:
            constats.append(('majeur', f'numero {num}',
                             f'cue number used {len(lignes_num)} times '
                             f'(lines {", ".join(str(x) for x in lignes_num)})'))

    total_ms = sum(c['fin'] - c['debut'] for c in cues if c['fin'] > c['debut'])
    return {'format': 'WebVTT' if vtt else 'SubRip', 'encodage': encodage,
            'langue': langue or 'default', 'cps_max': cps_max,
            'cues': len(cues), 'duree_dialogue_ms': total_ms,
            'caracteres': sum(len(c['texte']) for c in cues),
            'constats': constats}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('fichier')
    p.add_argument('--langue', help='target language code, sets the reading-speed limit')
    p.add_argument('--fps', type=float, default=25.0)
    p.add_argument('--duree', type=float, help='media duration in seconds')
    p.add_argument('--json', action='store_true')
    a = p.parse_args()

    if a.fps <= 0:
        print('error: --fps must be positive', file=sys.stderr)
        return 2
    try:
        r = analyser(a.fichier, a.langue, a.fps, a.duree)
    except (OSError, ValueError) as e:
        print(f'error: {e}', file=sys.stderr)
        return 2

    if a.json:
        json.dump(r, sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        print(f"{r['format']}, encoding {r['encodage']}, language {r['langue']} "
              f"(limit {r['cps_max']:.0f} char/s)")
        print(f"{r['cues']} cue(s), {r['caracteres']} characters, "
              f"{r['duree_dialogue_ms'] / 1000.0:.1f} s of dialogue")
        print()
        for niveau, ou, msg in r['constats'][:40]:
            print(f'[{niveau:<9}] {ou}: {msg}')
        if len(r['constats']) > 40:
            print(f'... and {len(r["constats"]) - 40} more')
        if not r['constats']:
            print('conformant on the points checked: timecodes, order, overlap, gap, '
                  'duration, reading speed, line length and count.')
    return 1 if r['constats'] else 0


if __name__ == '__main__':
    sys.exit(main())
