#!/usr/bin/env python3
# Copyright (C) 2026 SYNERGIELOC
#
# This file is part of "Localisation measurements".
# Licensed under the GNU Affero General Public License v3 or later.
# See the LICENSE file, or <https://www.gnu.org/licenses/>.
"""Reproduce every case the README claims, in one command.

    python verifier.py            # run them all
    python verifier.py -v         # print each case

It builds its own fixtures in a temporary directory, runs each tool as a
subprocess, and checks two things: the exit code, and - for the cases that were
worked out by hand - that the number printed is the number that was calculated.

No network, no third-party package, nothing written outside a temp directory.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent
OUTILS = RACINE / 'localisation'
BAVARD = '-v' in sys.argv or '--verbose' in sys.argv


# --------------------------------------------------------------------------
# Fixtures. "la" is exactly one syllable, which is what makes the dubbing
# arithmetic checkable without trusting the code that computes it.
# --------------------------------------------------------------------------
def la(n):
    return ' '.join(['la'] * n)


SRT = """1
00:00:01,000 --> 00:00:03,500
Bonjour, comment allez-vous ?

2
00:00:03,600 --> 00:00:07,000
Tres bien, merci beaucoup.
Et vous, depuis Paris ?

3
00:00:07,200 --> 00:00:09,000
Je rentre demain soir.

4
00:00:09,500 --> 00:00:11,000
[musique]
"""


def ecrire(d, nom, texte, enc='utf-8'):
    p = d / nom
    with open(p, 'w', encoding=enc, newline='\n') as f:
        f.write(texte)
    return p


def ecrire_json(d, nom, obj):
    return ecrire(d, nom, json.dumps(obj, ensure_ascii=False, indent=1))


def fixtures(d):
    import copy
    import re

    # ---- sous-titres
    ecrire(d, 'conforme.srt', SRT)
    ecrire(d, 'bom.srt', SRT, 'utf-8-sig')
    ecrire(d, 'cp1252.srt', SRT.replace('Tres bien', 'Très bien'), 'cp1252')
    vtt = re.sub(r'^\d+\n', '', 'WEBVTT\n\n' + SRT.replace(',', '.'), flags=re.M)
    ecrire(d, 'conforme.vtt', vtt)
    ecrire(d, 'chevauchement.srt', SRT.replace('00:00:03,600 -->', '00:00:03,000 -->'))
    ecrire(d, 'desordre.srt', SRT.replace('00:00:07,200 --> 00:00:09,000',
                                          '00:00:02,000 --> 00:00:02,800'))
    ecrire(d, 'trop-rapide.srt', SRT.replace(
        'Je rentre demain soir.', 'Je rentre demain soir et je repars aussitot.'))
    ecrire(d, 'ligne-longue.srt', SRT.replace(
        'Bonjour, comment allez-vous ?',
        'Bonjour, comment allez-vous donc ce matin a Strasbourg, cher ami ?'))
    ecrire(d, 'trois-lignes.srt', SRT.replace(
        'Tres bien, merci beaucoup.\nEt vous, depuis Paris ?',
        'Tres bien,\nmerci beaucoup.\nEt vous ?'))
    ecrire(d, 'trop-court.srt', SRT.replace('00:00:09,500 --> 00:00:11,000',
                                            '00:00:09,500 --> 00:00:09,900'))
    ecrire(d, 'trop-long.srt', SRT.replace('00:00:09,500 --> 00:00:11,000',
                                           '00:00:09,500 --> 00:00:17,000'))
    ecrire(d, 'fin-avant-debut.srt', SRT.replace('00:00:07,200 --> 00:00:09,000',
                                                 '00:00:09,000 --> 00:00:07,200'))
    ecrire(d, 'bloc-sans-timecode.srt', SRT.replace('00:00:03,600 --> 00:00:07,000',
                                                    '00:00:3,6 -> 00:00:7'))
    ecrire(d, 'tc-malforme.srt', SRT.replace('00:00:03,600 --> 00:00:07,000',
                                             '0:00:3,60 --> 00:00:07,000'))
    ecrire(d, 'cue-vide.srt', SRT.replace('Je rentre demain soir.\n', ''))
    ecrire(d, 'ecart-serre.srt', SRT.replace('00:00:07,200 -->', '00:00:07,020 -->'))
    ecrire(d, 'numero-double.srt', SRT.replace('\n3\n00:00:07,200', '\n2\n00:00:07,200'))
    ecrire(d, 'espaces.srt', SRT.replace('Je rentre demain soir.',
                                         '  Je rentre demain soir.  '))
    ecrire(d, 'vide.srt', '')

    # ---- doublage : 1 syllabe = 200 ms a 5 syll/s
    base = {'langue_source': 'en', 'langue_cible': 'fr', 'debit': {'fr': 5.0},
            'tolerance_etirement': 0.06, 'segments': [
                {'id': '1', 'debut': 1.0, 'fin': 3.0, 'locuteur': 'ANNA',
                 'voix': 'FR-F-01', 'original': 'We should go now.',
                 'traduction': la(10)},                       # 2000/2000 = 1.00
                {'id': '2', 'debut': 4.0, 'fin': 6.0, 'locuteur': 'BORIS',
                 'voix': 'FR-M-01', 'original': 'I told you so.',
                 'traduction': la(14)},                       # 2800/2000 = 1.40
                {'id': '3', 'debut': 7.0, 'fin': 11.0, 'locuteur': 'ANNA',
                 'voix': 'FR-F-01', 'original': 'Listen to me.',
                 'traduction': la(21)},                       # 4200/4000 = 1.05
                {'id': '4', 'debut': 12.0, 'fin': 14.0, 'locuteur': 'BORIS',
                 'voix': 'FR-M-01', 'original': 'No.',
                 'traduction': la(5)}]}                       # 1000/2000 = 0.50
    ecrire_json(d, 'segments-quatre-etats.json', base)

    tient = copy.deepcopy(base)
    tient['segments'] = [copy.deepcopy(base['segments'][0]),
                         {'id': '2', 'debut': 4.0, 'fin': 6.0, 'locuteur': 'BORIS',
                          'voix': 'FR-M-01', 'traduction': la(9)}]   # 0.90
    ecrire_json(d, 'segments-tient.json', tient)

    def seg(nom, f):
        x = copy.deepcopy(tient)
        f(x)
        ecrire_json(d, nom, x)

    seg('d-chevauchement-locuteur.json', lambda x: x['segments'].append(
        {'id': '3', 'debut': 2.0, 'fin': 2.5, 'locuteur': 'ANNA',
         'voix': 'FR-F-01', 'traduction': la(2)}))
    seg('d-deux-voix.json', lambda x: x['segments'].append(
        {'id': '3', 'debut': 8.0, 'fin': 10.0, 'locuteur': 'ANNA',
         'voix': 'FR-F-02', 'traduction': la(8)}))
    seg('d-voix-partagee.json', lambda x: x['segments'].append(
        {'id': '3', 'debut': 8.0, 'fin': 10.0, 'locuteur': 'CLARA',
         'voix': 'FR-F-01', 'traduction': la(8)}))
    seg('d-fin-avant-debut.json', lambda x: x['segments'][1].update(debut=6.0, fin=4.0))
    seg('d-sans-traduction.json', lambda x: x['segments'][1].update(traduction='   '))
    seg('d-id-double.json', lambda x: x['segments'][1].update(id='1'))
    seg('d-timecode.json', lambda x: x['segments'][1].update(debut='00:00:0x,000'))
    seg('d-sans-langue.json', lambda x: x.pop('langue_cible'))
    seg('d-langue-inconnue.json', lambda x: (x.update(langue_cible='xx'), x.pop('debit')))
    seg('d-debit-nul.json', lambda x: x.update(debit={'fr': 0}))
    seg('d-segments-vides.json', lambda x: x.update(segments=[]))
    tc = copy.deepcopy(tient)
    tc['segments'][0].update(debut='00:00:01,000', fin='00:00:03,000')
    ecrire_json(d, 'segments-timecode.json', tc)

    # ---- latence
    budget = {'cible_ms': 3000, 'etapes': [
        {'nom': 'chunk', 'p50': 250, 'p95': 250},
        {'nom': 'vad_commit', 'p50': 300, 'p95': 400},
        {'nom': 'asr', 'p50': 300, 'p95': 500},
        {'nom': 'mt', 'p50': 100, 'p95': 200},
        {'nom': 'tts', 'p50': 250, 'p95': 400},
        {'nom': 'playout', 'p50': 100, 'p95': 100}],
        'derive': {'expansion': 1.0, 'debit_source': 5.0,
                   'debit_tts': 6.0, 'part_parlee': 0.6}}
    ecrire_json(d, 'budget-tient.json', budget)

    def bud(nom, f):
        x = copy.deepcopy(budget)
        f(x)
        ecrire_json(d, nom, x)

    bud('b-latence.json', lambda x: x['etapes'][2].update(p50=2100, p95=2100))
    bud('b-p95.json', lambda x: x['etapes'][2].update(p95=2100))
    bud('b-derive.json', lambda x: x['derive'].update(expansion=1.25, debit_tts=5.0))
    bud('b-derive-limite.json', lambda x: x['derive'].update(debit_tts=5.0))
    bud('b-sans-derive.json', lambda x: x.pop('derive'))
    bud('b-sans-mt.json', lambda x: x.update(
        etapes=[e for e in x['etapes'] if e['nom'] != 'mt']))
    bud('b-chunk-long.json', lambda x: x['etapes'][0].update(p50=800, p95=800))
    bud('b-nom-double.json', lambda x: x['etapes'][1].update(nom='asr'))
    bud('b-p95-sous-p50.json', lambda x: x['etapes'][2].update(p95=100))
    bud('b-negatif.json', lambda x: x['etapes'][2].update(p50=-10))
    bud('b-etapes-vides.json', lambda x: x.update(etapes=[]))
    bud('b-cible-nulle.json', lambda x: x.update(cible_ms=0))
    bud('b-part-parlee.json', lambda x: x['derive'].update(part_parlee=1.5))
    bud('b-debit-nul.json', lambda x: x['derive'].update(debit_tts=0))
    bud('b-non-nombre.json', lambda x: x['etapes'][3].update(p50='vite'))

    # ---- terminologie
    ecrire_json(d, 'glossaire.json', {
        'langue_source': 'en', 'langue_cible': 'fr', 'termes': [
            {'source': 'provision', 'cible': 'provision',
             'interdits': ['approvisionnement']},
            {'source': 'deferred tax', 'cible': 'impot differe',
             'variantes': ['imposition differee']},
            {'source': 'headcount', 'cible': 'effectif'}]})
    saine = {'segments': [
        {'id': '1', 'source': 'We booked a provision of 1 200 000 euros.',
         'cible': 'Nous avons comptabilise une provision de 1 200 000 euros.'},
        {'id': '2', 'source': 'The deferred tax is 45 000.',
         'cible': "L'impot differe est de 45 000."},
        {'id': '3', 'source': 'Headcount stays at 38.',
         'cible': "L'effectif reste a 38."}]}
    ecrire_json(d, 'transcription-saine.json', saine)
    ecrire_json(d, 't-liste-nue.json', saine['segments'])

    def tra(nom, f):
        x = copy.deepcopy(saine)
        f(x)
        ecrire_json(d, nom, x)

    tra('t-interdit.json', lambda x: x['segments'][0].update(
        cible='Nous avons comptabilise un approvisionnement de 1 200 000 euros.'))
    tra('t-absent.json', lambda x: x['segments'][2].update(
        cible='Les equipes restent a 38.'))
    tra('t-non-traduit.json', lambda x: x['segments'][2].update(
        cible='Le headcount reste a 38.'))
    tra('t-chiffre-perdu.json', lambda x: x['segments'][0].update(
        cible='Nous avons comptabilise une provision importante.'))
    tra('t-chiffre-change.json', lambda x: x['segments'][1].update(
        cible="L'impot differe est de 54 000."))
    tra('t-chiffre-invente.json', lambda x: x['segments'][1].update(
        cible="L'impot differe est de 45 000 et 7 000."))
    tra('t-cible-vide.json', lambda x: x['segments'][1].update(cible='  '))
    tra('t-source-vide.json', lambda x: x['segments'][1].update(source=''))
    tra('t-variante.json', lambda x: x['segments'][1].update(
        cible="L'imposition differee est de 45 000."))
    tra('t-accents.json', lambda x: (
        x['segments'][0].update(
            cible='Nous avons comptabilise une PROVISION de 1 200 000 euros.'),
        x['segments'][1].update(cible="L'impôt différé est de 45 000.")))
    tra('t-separateurs.json', lambda x: x['segments'][0].update(
        cible='Nous avons comptabilise une provision de 1.200.000 euros.'))
    inc = copy.deepcopy(saine)
    inc['segments'].append({'id': '4', 'source': 'Another provision was released.',
                            'cible': 'Un autre approvisionnement a ete repris.'})
    ecrire_json(d, 't-incoherent.json', inc)

    for nom, g in (('g-vide.json', {'termes': []}),
                   ('g-sans-cible.json', {'termes': [{'source': 'provision'}]}),
                   ('g-doublon.json', {'termes': [
                       {'source': 'provision', 'cible': 'provision'},
                       {'source': 'Provision', 'cible': 'dotation'}]}),
                   ('g-interdits-non-liste.json', {'termes': [
                       {'source': 'a', 'cible': 'b', 'interdits': 'c'}]})):
        ecrire_json(d, nom, g)


# --------------------------------------------------------------------------
# The cases. 0 = conformant, 1 = findings, 2 = refused input.
# A third element lists strings that must appear - those are the numbers that
# were worked out by hand before the code existed.
# --------------------------------------------------------------------------
def cas():
    ST, AJ = 'valider_sous_titres.py', 'ajuster_doublage.py'
    BL, GT = 'budget_latence.py', 'glossaire_terminologie.py'
    return [
        # --- timed text
        (ST, ['conforme.srt', '--langue', 'fr'], 0, ['conformant on the points']),
        (ST, ['conforme.vtt'], 0, ['WebVTT']),
        (ST, ['bom.srt'], 0, ['UTF-8 with BOM']),
        (ST, ['cp1252.srt'], 0, ['cp1252']),
        (ST, ['chevauchement.srt'], 1, ['overlaps the previous cue by 500 ms']),
        (ST, ['desordre.srt'], 1, ['out of order']),
        (ST, ['trop-rapide.srt', '--langue', 'fr'], 1, ['24.4 char/s']),
        (ST, ['ligne-longue.srt'], 1, ['66 characters, over 42']),
        (ST, ['trois-lignes.srt'], 1, ['3 lines, over 2']),
        (ST, ['trop-court.srt'], 1, ['400 ms: under 1000 ms']),
        (ST, ['trop-long.srt'], 1, ['7500 ms: over 7000 ms']),
        (ST, ['fin-avant-debut.srt'], 1, ['ends before it starts']),
        (ST, ['bloc-sans-timecode.srt'], 1, ['block with no timecode']),
        (ST, ['tc-malforme.srt'], 1, ['unreadable timecode']),
        (ST, ['cue-vide.srt'], 1, ['timecode and no text']),
        (ST, ['ecart-serre.srt'], 1, ['20 ms after the previous cue']),
        (ST, ['numero-double.srt'], 1, ['used 2 times']),
        (ST, ['espaces.srt'], 1, ['leading or trailing spaces']),
        (ST, ['conforme.srt', '--duree', '10'], 1, ['past the 10000 ms']),
        (ST, ['conforme.srt', '--langue', 'ja'], 1, ['above 7']),
        (ST, ['conforme.srt', '--fps', '0'], 2, ['--fps must be positive']),
        (ST, ['vide.srt'], 2, ['empty file']),
        (ST, ['absent.srt'], 2, []),

        # --- dubbing fit, every number below was calculated by hand first
        (AJ, ['segments-tient.json'], 0, ['every line fits']),
        (AJ, ['segments-timecode.json'], 0, []),
        (AJ, ['segments-quatre-etats.json'], 1,
         ['1.40x', 'cut about 4 syll, or 680 ms', '1.05x', '5.0% time-stretch',
          '0.50x', '680 ms to recover']),
        (AJ, ['d-chevauchement-locuteur.json'], 1, ['one mouth, two lines']),
        (AJ, ['d-deux-voix.json'], 1, ['cast to 2 different voices']),
        (AJ, ['d-voix-partagee.json'], 1, ['one voice for 2 characters']),
        (AJ, ['d-fin-avant-debut.json'], 1, ['ends before it starts']),
        (AJ, ['d-sans-traduction.json'], 1, ['no translation']),
        (AJ, ['d-id-double.json'], 1, ['segment id used twice']),
        (AJ, ['d-timecode.json'], 2, ['is not a timecode']),
        (AJ, ['d-sans-langue.json'], 2, ['"langue_cible" is required']),
        (AJ, ['d-langue-inconnue.json'], 2, ['no speaking rate']),
        (AJ, ['d-debit-nul.json'], 2, ['must be positive']),
        (AJ, ['d-segments-vides.json'], 2, ['non-empty list']),
        (AJ, ['segments-tient.json', '--modele', 'xyz'], 2, ['syllabes or caracteres']),
        (AJ, ['segments-tient.json', '--modele'], 2, ['syllabes or caracteres']),
        (AJ, ['absent.json'], 2, []),

        # --- latency and drift
        (BL, ['budget-tient.json'], 0, ['1300', '1587', '1850', 'holds']),
        (BL, ['b-latence.json'], 1, ['3100 ms over the 3000 ms', 'cut 100 ms']),
        (BL, ['b-p95.json'], 1, ['3112 ms does not']),
        (BL, ['b-derive.json'], 1, ['9.00 s per minute', '270 s', '6.25']),
        (BL, ['b-derive-limite.json'], 1, ['break-even']),
        (BL, ['b-sans-derive.json'], 1, ['no "derive" block']),
        (BL, ['b-sans-mt.json'], 1, ['always holds']),
        (BL, ['b-chunk-long.json'], 1, ['structural']),
        (BL, ['b-nom-double.json'], 1, ['stage name used twice']),
        (BL, ['b-p95-sous-p50.json'], 2, ['is below p50']),
        (BL, ['b-negatif.json'], 2, ['is negative']),
        (BL, ['b-etapes-vides.json'], 2, ['non-empty list']),
        (BL, ['b-cible-nulle.json'], 2, ['must be positive']),
        (BL, ['b-part-parlee.json'], 2, ['part_parlee']),
        (BL, ['b-debit-nul.json'], 2, ['must be positive']),
        (BL, ['b-non-nombre.json'], 2, ['is not a number']),
        (BL, ['absent.json'], 2, []),
        (BL, ['budget-tient.json', 'budget-tient.json'], 2, ['usage:']),

        # --- terminology and figures
        (GT, ['glossaire.json', 'transcription-saine.json'], 0, ['terminology holds']),
        (GT, ['glossaire.json', 't-variante.json'], 0, []),
        (GT, ['glossaire.json', 't-accents.json'], 0, []),
        (GT, ['glossaire.json', 't-separateurs.json'], 0, []),
        (GT, ['glossaire.json', 't-liste-nue.json'], 0, []),
        (GT, ['glossaire.json', 't-interdit.json'], 1, ['glossary forbids']),
        (GT, ['glossaire.json', 't-absent.json'], 1, ['is not in']),
        (GT, ['glossaire.json', 't-non-traduit.json'], 1, ['left in the source language']),
        (GT, ['glossaire.json', 't-chiffre-perdu.json'], 1, ['1200000 in the source']),
        (GT, ['glossaire.json', 't-chiffre-change.json'], 1,
         ['altered: 45000 said, 54000 interpreted']),
        (GT, ['glossaire.json', 't-chiffre-invente.json'], 1, ['7000 in the interpretation']),
        (GT, ['glossaire.json', 't-cible-vide.json'], 1, ['target empty']),
        (GT, ['glossaire.json', 't-source-vide.json'], 1, ['no source text']),
        (GT, ['glossaire.json', 't-incoherent.json'], 1, ['2 different ways']),
        (GT, ['g-vide.json', 'transcription-saine.json'], 2, ['non-empty list']),
        (GT, ['g-sans-cible.json', 'transcription-saine.json'], 2, ['are required']),
        (GT, ['g-doublon.json', 'transcription-saine.json'], 2, ['twice']),
        (GT, ['g-interdits-non-liste.json', 'transcription-saine.json'], 2,
         ['must be a list']),
        (GT, ['glossaire.json'], 2, ['usage:']),
        (GT, ['glossaire.json', 'absent.json'], 2, ['transcript unreadable']),
    ]


def main():
    d = Path(tempfile.mkdtemp(prefix='localisation-verif-'))
    try:
        fixtures(d)
        total = reussis = 0
        echecs = []
        for script, args, attendu, motifs in cas():
            total += 1
            cmd = [sys.executable, '-I', str(OUTILS / script)]
            cmd += [a if a.startswith('--') or not a.endswith(('.srt', '.vtt', '.json'))
                    else str(d / a) for a in args]
            p = subprocess.run(cmd, capture_output=True, text=True,
                               encoding='utf-8', errors='replace')
            sortie = (p.stdout or '') + (p.stderr or '')
            ok = p.returncode == attendu
            absents = [m for m in motifs if m not in sortie]
            if absents:
                ok = False
            etiquette = f'{script} {" ".join(args)}'
            if ok:
                reussis += 1
                if BAVARD:
                    print(f'  ok   {etiquette}')
            else:
                detail = (f'exit {p.returncode}, expected {attendu}' if p.returncode != attendu
                          else f'missing from output: {absents}')
                echecs.append(f'{etiquette}  ->  {detail}')
                print(f'  FAIL {etiquette}  ->  {detail}')

        print()
        print(f'  {reussis}/{total} cases pass')
        if echecs:
            print(f'  {len(echecs)} failure(s)')
            return 1
        print('  Exit codes and the hand-calculated numbers all match.')
        return 0
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
