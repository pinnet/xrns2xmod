#!/usr/bin/env python3
"""Checks check_mod.py itself: builds the MOD each test song *should* convert to and
expects every check to pass, then breaks each one and expects a failure.
Usage: python3 selftest.py [songs_dir]
"""
import copy
import glob
import json
import os
import subprocess
import sys
import tempfile

import modfile

HERE = os.path.dirname(os.path.abspath(__file__))
SONGS = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, 'songs')


def concrete(param):
    return {'>0': 0x10, 'x>0': 0x10, 'y>0': 0x01}.get(param) if param in ('>0', 'x>0', 'y>0') else int(param, 16)


def ideal(e):
    m = modfile.Mod()
    m.samples = [modfile.Sample('test %d' % i, 1024, 0, 64, 0, 1024, bytes(1024)) for i in range(31)]
    length = e.get('song_length', 1)
    m.order = list(range(length))
    for a, b in e.get('same_pattern', []):
        m.order[b] = m.order[a]
    used = sorted(set(m.order))
    m.order = [used.index(p) for p in m.order]
    m.patterns = [[[modfile.Cell() for _ in range(4)] for _ in range(64)] for _ in used]
    if 'short_pattern' in e:
        sp = e['short_pattern']
        m.cell(sp['pos'], sp['lines'] - 1, 3).effect = 0xD
    if 'notes_run' in e:
        n = e['notes_run']
        start = modfile.PERIODS.index(next(p for p in modfile.PERIODS if modfile.note_name(p) == n['first']))
        for i in range(n['count']):
            c = m.cell(n['pos'], n['first_row'] + i, n['ch'])
            c.period, c.sample = modfile.PERIODS[start + i], 1
    for c in e.get('cells', []):
        cell = m.cell(c['pos'], c['row'], c['ch'])
        if 'note' in c:
            cell.period = 0 if c['note'] == '---' else next(p for p in modfile.PERIODS if modfile.note_name(p) == c['note'])
        if 'sample' in c:
            cell.sample = c['sample']
        if 'effect' in c:
            cell.effect, cell.param = int(c['effect'], 16), concrete(c['param'])
    for c in e.get('effects_anywhere_in_row', []):
        row = m.patterns[m.order[c['pos']]][c['row']]
        free = next(x for x in row if x.effect == 0 and x.param == 0)
        free.effect, free.param = int(c['effect'], 16), concrete(c['param'])
    if 'samples_used' in e:
        for i in range(e['samples_used']):
            m.patterns[0][i % 64][3].sample = m.patterns[0][i % 64][3].sample or 0
    return m


def run(e_path, m):
    with tempfile.NamedTemporaryFile(suffix='.mod', delete=False) as f:
        path = f.name
    modfile.write(path, m)
    r = subprocess.run([sys.executable, os.path.join(HERE, 'check_mod.py'), e_path, path], capture_output=True, text=True)
    os.unlink(path)
    return r.returncode, r.stdout


def breakages(m):
    """Ways a converter could go wrong; each should make the check fail."""
    out = []
    b = copy.deepcopy(m); b.signature = '6CHN'; out.append(('six-channel MOD', b))
    b = copy.deepcopy(m); b.patterns[0][5][0].period = 113; out.append(('B-3 note', b))
    b = copy.deepcopy(m); b.patterns[0][6][1].effect, b.patterns[0][6][1].param = 0xF, 0; out.append(('F00', b))
    b = copy.deepcopy(m); b.samples[0].volume = 65; out.append(('sample volume 65', b))
    b = copy.deepcopy(m); b.samples[0].data = b.samples[0].data[:100]; out.append(('sample data cut short', b))
    b = copy.deepcopy(m); b.samples[0].loop_start = 1000; out.append(('loop past the end', b))
    return out


failures = 0
for e_path in sorted(glob.glob(os.path.join(SONGS, '*.json'))):
    e = json.load(open(e_path))
    if e['expect'] != 'convert':
        continue
    m = ideal(e)
    code, out = run(e_path, m)
    name = os.path.basename(e_path)
    if code != 0:
        failures += 1
        print('FAIL %s: the ideal MOD should pass\n%s' % (name, out))
    else:
        print('ok   %s: ideal MOD passes (%d checks)' % (name, out.count('PASS')))
    for what, broken in breakages(m):
        code, out = run(e_path, broken)
        if code == 0:
            failures += 1
            print('FAIL %s: a MOD with a %s should fail' % (name, what))
    # Each expected cell, wrong on its own, should fail too.
    for i, c in enumerate(e.get('cells', [])):
        b = copy.deepcopy(m)
        cell = b.cell(c['pos'], c['row'], c['ch'])
        if 'effect' in c:
            cell.effect = (cell.effect + 1) % 16
        elif 'note' in c:
            cell.period = 856 if cell.period != 856 else 808
        else:
            cell.sample = (cell.sample % 31) + 1
        code, _ = run(e_path, b)
        if code == 0:
            failures += 1
            print('FAIL %s: wrong cell %d not caught' % (name, i))
print('selftest: %s' % ('all good' if not failures else '%d problems' % failures))
sys.exit(1 if failures else 0)
