# Copyright (C) 2026 SYNERGIELOC
#
# This file is part of "Localisation measurements".
# Licensed under the GNU Affero General Public License v3 or later.
# See the LICENSE file, or <https://www.gnu.org/licenses/>.
"""Measurements for an offline localisation pipeline.

Four checks that decide whether a dub or a live interpretation is usable:

- valider_sous_titres   : timed text a broadcaster will accept
- ajuster_doublage      : does the translated line fit the mouth
- budget_latence        : latency, and the drift nobody computes
- glossaire_terminologie: terminology held, and every figure carried over

Standard library only. No network. Each one reads its input and writes nothing.
Run `python verifier.py` to reproduce every case.
"""
__all__ = ['valider_sous_titres', 'ajuster_doublage',
           'budget_latence', 'glossaire_terminologie']
