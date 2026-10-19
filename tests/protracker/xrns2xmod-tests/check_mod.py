#!/usr/bin/env python3
"""Check a converted MOD against ProTracker's limits and a test song's expectations.

Usage: check_mod.py <expectations.json> <converted.mod | ->
Pass '-' for the MOD when the converter produced none (a refusal).
Prints one line per check and exits 1 if any failed.
"""
import json
import os
import sys

import modfile

# What the game's player (ptplayer, from ProTracker 2.3) and a real A1200 can play.
MAX_SAMPLE_BYTES = 131070
SAFE_PERIODS = modfile.PERIODS[:-2]       # C-1 to A-3; A#3 and B-3 distort on an A1200
PT_EFFECTS = set(range(16))
UNUSED_E = {0x8}                          # E8x does nothing in ProTracker 2.3


class Report:
    def __init__(self):
        self.failed = 0

    def check(self, ok, what, detail=''):
        print('  %s  %s%s' % ('PASS' if ok else 'FAIL', what, ('  (' + detail + ')') if detail else ''))
        if not ok:
            self.failed += 1


def param_ok(want, got):
    """want: '37' exact hex, '>0' any non-zero, 'x>0' upper nibble set only, 'y>0' lower only, 'A?' upper nibble A and lower non-zero."""
    if want == '>0':
        return got > 0
    if want == 'x>0':
        return got >> 4 > 0 and got & 15 == 0
    if want == 'y>0':
        return got & 15 > 0 and got >> 4 == 0
    if len(want) == 2 and want[1] == '?':      # 'A?' = upper nibble A, lower nibble non-zero
        return got >> 4 == int(want[0], 16) and got & 15 > 0
    return got == int(want, 16)


def check_limits(m, r):
    r.check(m.signature == 'M.K.', 'signature is M.K. (4 channels, up to 64 patterns)', m.signature)
    r.check(1 <= len(m.order) <= 128, 'song length 1-128', str(len(m.order)))
    r.check(len(m.patterns) <= 64, 'at most 64 patterns', str(len(m.patterns)))
    bad = [i + 1 for i, s in enumerate(m.samples) if s.length > MAX_SAMPLE_BYTES]
    r.check(not bad, 'every sample under 128 KB', 'too long: %s' % bad if bad else '')
    bad = [i + 1 for i, s in enumerate(m.samples)
           if s.length and s.loop_length > 2 and s.loop_start + s.loop_length > s.length]
    r.check(not bad, 'loops stay inside their samples', 'bad: %s' % bad if bad else '')
    bad = [i + 1 for i, s in enumerate(m.samples) if s.volume > 64]
    r.check(not bad, 'sample volumes 0-64', 'bad: %s' % bad if bad else '')
    r.check(m.trailing >= 0, 'file holds all the sample data it declares',
            'short by %d bytes' % -m.trailing if m.trailing < 0 else '')
    periods, effects, speeds, samples = set(), [], [], set()
    for pi, pat in enumerate(m.patterns):
        for ri, row in enumerate(pat):
            for ci, c in enumerate(row):
                if c.period:
                    periods.add(c.period)
                if c.sample:
                    samples.add(c.sample)
                if c.effect == 0xE and c.param >> 4 in UNUSED_E:
                    effects.append('pattern %d row %d ch %d: E%02X' % (pi, ri, ci + 1, c.param))
                if c.effect == 0xF and c.param == 0:
                    speeds.append('pattern %d row %d ch %d: F00 (stops the song)' % (pi, ri, ci + 1))
    unsafe = sorted(p for p in periods if p not in SAFE_PERIODS)
    r.check(not unsafe, 'every note between C-1 and A-3',
            'outside: %s' % ', '.join(modfile.note_name(p) for p in unsafe) if unsafe else '')
    r.check(not effects, 'no effects ProTracker ignores', '; '.join(effects[:5]))
    r.check(not speeds, 'no F00 (it stops the song)', '; '.join(speeds[:5]))
    bad = sorted(s for s in samples if s > 31 or not m.samples[s - 1].length)
    r.check(not bad, 'every sample played exists', 'missing: %s' % bad if bad else '')
    return samples


def check_expectations(m, e, r, samples_played):
    for c in e.get('cells', []):
        try:
            cell = m.cell(c['pos'], c['row'], c['ch'])
        except IndexError:
            r.check(False, 'position %d row %d channel %d exists' % (c['pos'], c['row'], c['ch'] + 1))
            continue
        where = 'pos %d row %02d ch %d' % (c['pos'], c['row'], c['ch'] + 1)
        label = (' from %s' % c['renoise']) if 'renoise' in c else ''
        if 'note' in c:
            r.check(modfile.note_name(cell.period) == c['note'], '%s note %s' % (where, c['note']),
                    'got %s' % modfile.note_name(cell.period))
        if 'sample' in c:
            r.check(cell.sample == c['sample'], '%s sample %d' % (where, c['sample']), 'got %d' % cell.sample)
        if 'effect' in c:
            ok = cell.effect == int(c['effect'], 16) and param_ok(c['param'], cell.param)
            for alt_effect, alt_param in c.get('alt', []):
                ok = ok or (cell.effect == int(alt_effect, 16) and param_ok(alt_param, cell.param))
            r.check(ok, '%s effect %s%s%s' % (where, c['effect'], c['param'], label),
                    'got %X%02X' % (cell.effect, cell.param))
    for c in e.get('effects_anywhere_in_row', []):
        row = m.cell(c['pos'], c['row'], 0) and m.patterns[m.order[c['pos']]][c['row']]
        ok = any(x.effect == int(c['effect'], 16) and param_ok(c['param'], x.param) for x in row)
        got = ' '.join('%X%02X' % (x.effect, x.param) for x in row)
        r.check(ok, 'pos %d row %02d has %s%s from %s' % (c['pos'], c['row'], c['effect'], c['param'], c['renoise']),
                'row has %s' % got)
    if 'notes_run' in e:
        n = e['notes_run']
        got = [m.cell(n['pos'], n['first_row'] + i, n['ch']).period for i in range(n['count'])]
        names = [modfile.note_name(p) for p in got]
        first_ok = names[0] == n['first']
        steps_ok = all(p in modfile.PERIODS for p in got) and all(
            modfile.PERIODS.index(b) == modfile.PERIODS.index(a) + 1 for a, b in zip(got, got[1:]))
        r.check(first_ok, 'lowest note comes out as %s' % n['first'], 'got %s' % names[0])
        r.check(steps_ok, '%d notes rise one semitone per row' % n['count'], ' '.join(names))
    if 'song_length' in e:
        r.check(len(m.order) == e['song_length'], 'song length %d' % e['song_length'], 'got %d' % len(m.order))
    for a, b in e.get('same_pattern', []):
        r.check(m.order[a] == m.order[b], 'positions %d and %d play the same pattern' % (a, b),
                'order %s' % m.order)
    if 'short_pattern' in e:
        sp = e['short_pattern']
        pat = m.patterns[m.order[sp['pos']]]
        breaks = [i for i, row in enumerate(pat) if any(c.effect == 0xD for c in row)]
        r.check(breaks and breaks[0] == sp['lines'] - 1,
                'the %d-line pattern ends with a pattern break on row %d' % (sp['lines'], sp['lines'] - 1),
                'breaks on rows %s' % breaks if breaks else 'no break: it plays 64 rows')
    if 'samples_used' in e:
        r.check(len(samples_played) == e['samples_used'], '%d different samples played' % e['samples_used'],
                'got %d' % len(samples_played))


def main():
    e = json.load(open(sys.argv[1]))
    mod_path = sys.argv[2]
    r = Report()
    print('%s: %s' % (e['song'], e['what']))
    produced = mod_path != '-' and os.path.exists(mod_path)
    if e['expect'] == 'refuse':
        r.check(not produced, 'converter refuses it')
    elif e['expect'] == 'refuse_or_4ch':
        if produced:
            try:
                m = modfile.read(mod_path)
                r.check(True, 'converter kept it to a 4-channel MOD (%s)' % m.signature)
            except ValueError as err:
                r.check(False, 'converter refuses it or keeps it 4-channel', str(err))
        else:
            r.check(True, 'converter refuses it')
    else:
        r.check(produced, 'converter produced a MOD')
        if produced:
            try:
                m = modfile.read(mod_path)
            except ValueError as err:
                r.check(False, 'MOD is readable as 4-channel ProTracker', str(err))
            else:
                played = check_limits(m, r)
                check_expectations(m, e, r, played)
    sys.exit(1 if r.failed else 0)


if __name__ == '__main__':
    main()
