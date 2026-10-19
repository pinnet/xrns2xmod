#!/usr/bin/env python3
"""Build Renoise test songs that stay within ProTracker's limits, plus what each
should turn into once converted to MOD.

Every song starts from Xrns2XMod's own empty MOD template (4 tracks, 125 BPM,
4 lines per beat, 6 ticks per line) with instruments copied from one of its
example songs. Samples are 8363 Hz mono WAVs with base note C-4, so Renoise C-3
should come out as ProTracker C-1.

Writes songs/<name>.xrns and songs/<name>.json (the expectations check_mod.py reads).
Usage: python3 make_test_songs.py <path to an xrns2xmod checkout> [out_dir]
"""
import copy
import io
import json
import math
import os
import struct
import sys
import wave
import xml.etree.ElementTree as ET
import zipfile

SRC = sys.argv[1] if len(sys.argv) > 1 else '../xrns2xmod'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'songs')
TEMPLATE = os.path.join(SRC, 'Xrns2XMod/resources/templates/empty_mod.xrns')
INSTRUMENT_DONOR = os.path.join(SRC, 'Xrns2XMod/resources/examples/test_sample_commands.xrns')
NOTE_NAMES = ['C-', 'C#', 'D-', 'D#', 'E-', 'F-', 'F#', 'G-', 'G#', 'A-', 'A#', 'B-']
RATE = 8363
CYCLE = 32           # samples per wave cycle: about 261 Hz at 8363 Hz
SAMPLE_FRAMES = 1024


def renoise_note(name_or_index):
    if isinstance(name_or_index, str):
        return name_or_index
    return '%s%d' % (NOTE_NAMES[name_or_index % 12], name_or_index // 12)


def make_wav(shape):
    """A looped single-pitch wave, different for each instrument so they're tellable apart."""
    frames = bytearray()
    for i in range(SAMPLE_FRAMES):
        phase = (i % CYCLE) / CYCLE
        if shape % 3 == 0:
            v = 0.6 if phase < 0.25 + 0.05 * (shape % 5) else -0.6
        elif shape % 3 == 1:
            v = 0.6 * (2 * phase - 1)
        else:
            v = 0.6 * math.sin(2 * math.pi * phase)
        frames += struct.pack('<h', int(v * 32767))
    buf = io.BytesIO()
    w = wave.open(buf, 'wb')
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes(bytes(frames))
    w.close()
    return buf.getvalue()


def sub(parent, tag, text=None):
    e = ET.SubElement(parent, tag)
    if text is not None:
        e.text = str(text)
    return e


class Song:
    def __init__(self, instruments=1, tracks=4):
        self.tree = ET.ElementTree(ET.fromstring(zipfile.ZipFile(TEMPLATE).read('Song.xml')))
        self.root = self.tree.getroot()
        donor = ET.fromstring(zipfile.ZipFile(INSTRUMENT_DONOR).read('Song.xml'))
        donor_inst = donor.find('Instruments/Instrument')
        insts = self.root.find('Instruments')
        for old in list(insts):
            insts.remove(old)
        self.samples = {}
        for i in range(instruments):
            inst = copy.deepcopy(donor_inst)
            name = 'Test %02d' % (i + 1)
            inst.find('Name').text = name
            sample = inst.find('SampleGenerator/Samples/Sample')
            sample.find('Name').text = name
            sample.find('LoopMode').text = 'Forward'
            sample.find('LoopStart').text = '0'
            sample.find('LoopEnd').text = str(SAMPLE_FRAMES - 1)
            sample.find('Mapping/BaseNote').text = '48'
            for tag in ('DisplayStart', 'DisplayLength'):
                if sample.find(tag) is not None:
                    sample.find(tag).text = '0' if tag == 'DisplayStart' else str(SAMPLE_FRAMES)
            insts.append(inst)
            self.samples['SampleData/Instrument%02d (%s)/Sample00 (%s).wav' % (i, name, name)] = make_wav(i)
        # Extra tracks (only for the over-the-limit test).
        seq_tracks = self.root.find('Tracks')
        normal = seq_tracks.findall('SequencerTrack')
        for _ in range(tracks - len(normal)):
            seq_tracks.insert(len(seq_tracks.findall('SequencerTrack')), copy.deepcopy(normal[0]))
        self.tracks = tracks
        self.pattern_template = copy.deepcopy(self.root.find('PatternPool/Patterns/Pattern'))
        self.root.find('PatternPool/Patterns').clear()
        self.patterns = []

    def add_pattern(self, lines=64):
        pat = copy.deepcopy(self.pattern_template)
        pat.find('NumberOfLines').text = str(lines)
        ptracks = pat.find('Tracks')
        normal = ptracks.findall('PatternTrack')
        for _ in range(self.tracks - len(normal)):
            ptracks.insert(len(ptracks.findall('PatternTrack')), copy.deepcopy(normal[0]))
        self.root.find('PatternPool/Patterns').append(pat)
        self.patterns.append({})
        return len(self.patterns) - 1

    def put(self, pattern, track, line, note=None, inst=None, vol=None, fx=None):
        """track 0-3 are note tracks, 'master' is the master track. fx = ('0A', '37')."""
        self.patterns[pattern].setdefault(track, {}).setdefault(line, []).append((note, inst, vol, fx))

    def sequence(self, order):
        entries = self.root.find('PatternSequence/SequenceEntries')
        template = copy.deepcopy(entries.find('SequenceEntry'))
        entries.clear()
        for p in order:
            e = copy.deepcopy(template)
            e.find('Pattern').text = str(p)
            entries.append(e)

    def _write_lines(self):
        for pat, data in zip(self.root.findall('PatternPool/Patterns/Pattern'), self.patterns):
            ptracks = pat.find('Tracks')
            note_tracks = ptracks.findall('PatternTrack')
            master = ptracks.find('PatternMasterTrack')
            for key, lines in data.items():
                track = master if key == 'master' else note_tracks[key]
                lines_el = track.find('Lines')
                if lines_el is None:
                    # Renoise writes <Lines> straight after the preset fields; keep that order.
                    lines_el = ET.Element('Lines')
                    tags = [child.tag for child in track]
                    track.insert(tags.index('SelectedPresetIsModified') + 1, lines_el)
                for index in sorted(lines):
                    line = sub(lines_el, 'Line')
                    line.set('index', str(index))
                    note, inst, vol, fx = lines[index][0]
                    if key != 'master':
                        nc = sub(sub(line, 'NoteColumns'), 'NoteColumn')
                        if note is not None:
                            sub(nc, 'Note', renoise_note(note))
                        if inst is not None:
                            sub(nc, 'Instrument', '%02X' % inst)
                        if vol is not None:
                            sub(nc, 'Volume', vol)
                    ec = sub(sub(line, 'EffectColumns'), 'EffectColumn')
                    if fx is not None:
                        sub(ec, 'Value', fx[1])
                        sub(ec, 'Number', fx[0])

    def save(self, name, expect):
        self._write_lines()
        os.makedirs(OUT, exist_ok=True)
        xml = ET.tostring(self.root, encoding='UTF-8', xml_declaration=True)
        with zipfile.ZipFile(os.path.join(OUT, name + '.xrns'), 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('Song.xml', xml)
            for path, data in self.samples.items():
                z.writestr(path, data)
        expect = dict(expect, song=name + '.xrns')
        with open(os.path.join(OUT, name + '.json'), 'w') as f:
            json.dump(expect, f, indent=1)


def notes_test():
    """ProTracker's whole safe range: Renoise C-3 to A-5 should be C-1 to A-3, one per row."""
    s = Song()
    p = s.add_pattern()
    for i in range(34):
        s.put(p, 0, i, note=36 + i, inst=0)
    s.sequence([p])
    s.save('pt_notes', {
        'what': 'Every note ProTracker can play safely on an A1200, in order',
        'expect': 'convert',
        'notes_run': {'pos': 0, 'ch': 0, 'first_row': 0, 'count': 34, 'first': 'C-1'},
        'cells': [{'pos': 0, 'row': 0, 'ch': 0, 'sample': 1}],
    })


def note_too_high_test():
    """B-3 is the top of ProTracker's table but distorts on a real A1200. The converter
    reports a too-high note as an error and drops it from the MOD, still writing the file
    (checked in its source and on a real run), so the test is that the note is gone."""
    s = Song()
    p = s.add_pattern()
    s.put(p, 0, 0, note='B-5', inst=0)
    s.sequence([p])
    s.save('pt_note_too_high', {
        'what': 'A note above A-3 must be dropped, not written, in hardware mode',
        'expect': 'convert',
        'cells': [{'pos': 0, 'row': 0, 'ch': 0, 'note': '---', 'renoise': 'B-5 (too high)'}],
    })


def four_tracks_test():
    s = Song(instruments=4)
    p = s.add_pattern()
    for t, note in enumerate(['C-4', 'E-4', 'G-4', 'C-5']):
        s.put(p, t, 0, note=note, inst=t)
    s.sequence([p])
    s.save('pt_four_tracks', {
        'what': 'One note on each of the 4 tracks, each with its own sample',
        'expect': 'convert',
        'cells': [
            {'pos': 0, 'row': 0, 'ch': 0, 'note': 'C-2', 'sample': 1},
            {'pos': 0, 'row': 0, 'ch': 1, 'note': 'E-2', 'sample': 2},
            {'pos': 0, 'row': 0, 'ch': 2, 'note': 'G-2', 'sample': 3},
            {'pos': 0, 'row': 0, 'ch': 3, 'note': 'C-3', 'sample': 4},
        ],
    })


def effects_test():
    """Each ProTracker effect we plan to use, one row at a time on track 1, plus global
    commands on the master track."""
    s = Song()
    p = s.add_pattern()
    rows = [
        # (line, note, vol, fx, expected MOD effect, expected param)
        (0, 'C-4', None, ('0A', '37'), '0', '37'),          # arpeggio
        (4, 'C-4', None, ('0V', '48'), '4', '48'),          # vibrato
        (8, 'C-4', None, ('0U', '10'), '1', '>0'),          # slide up
        (12, 'C-4', None, ('0D', '10'), '2', '>0'),         # slide down
        (16, 'C-4', None, None, None, None),
        (17, 'E-4', None, ('0G', '10'), '3', '>0'),         # glide to E-4
        (20, 'C-4', '20', None, 'C', '10'),                 # volume column 20 of 80 = 16 of 64
        (24, 'C-4', None, ('0I', '10'), 'A', 'x>0'),        # volume slide up
        (28, None, None, ('0O', '10'), 'A', 'y>0'),         # volume slide down
        (32, 'C-4', None, ('0S', '80'), '9', '>0'),         # sample offset (halfway)
        (36, 'C-4', None, ('0R', '03'), 'E', '93'),         # retrigger every 3 ticks
        (40, 'C-4', None, ('0Q', '03'), 'E', 'D3'),         # note delay 3 ticks
        (44, 'C-4', None, None, None, None),
        (46, 'OFF', None, None, 'C', '00'),                 # note off = volume 0
    ]
    cells = []
    for line, note, vol, fx, effect, param in rows:
        s.put(p, 0, line, note=note, inst=0 if note not in (None, 'OFF') else None, vol=vol, fx=fx)
        if effect is not None:
            cell = {'pos': 0, 'row': line, 'ch': 0, 'effect': effect, 'param': param,
                    'renoise': '%s %s' % ((fx[0] + fx[1]) if fx else 'vol ' + (vol or 'OFF'), note or '')}
            if fx and fx[0] in ('0I', '0O'):
                # the converter turns a per-row step into a fine volume slide (EAx / EBx) when it fits
                cell['alt'] = [('E', 'A?' if fx[0] == '0I' else 'B?')]
            cells.append(cell)
    s.put(p, 'master', 0, fx=('ZK', '04'))
    s.put(p, 'master', 1, fx=('ZT', '8C'))
    s.put(p, 'master', 63, fx=('ZB', '00'))
    s.sequence([p])
    s.save('pt_effects', {
        'what': 'The ProTracker effects we plan to use, and speed, tempo and pattern break',
        'expect': 'convert',
        'cells': cells,
        'effects_anywhere_in_row': [
            {'pos': 0, 'row': 0, 'effect': 'F', 'param': '04', 'renoise': 'ZK04 speed 4'},
            {'pos': 0, 'row': 1, 'effect': 'F', 'param': '8C', 'renoise': 'ZT8C tempo 140'},
            {'pos': 0, 'row': 63, 'effect': 'D', 'param': '00', 'renoise': 'ZB00 pattern break'},
        ],
    })


def structure_test():
    """Patterns reused in the sequence, and a 32-line pattern (MOD patterns are always 64 rows)."""
    s = Song()
    a, b, c = s.add_pattern(64), s.add_pattern(32), s.add_pattern(64)
    s.put(a, 0, 0, note='C-4', inst=0)
    s.put(b, 0, 0, note='E-4', inst=0)
    s.put(c, 0, 0, note='G-4', inst=0)
    s.sequence([a, b, a, c])
    s.save('pt_structure', {
        'what': 'A 4-position sequence that reuses a pattern, with one 32-line pattern',
        'expect': 'convert',
        'song_length': 4,
        'same_pattern': [[0, 2]],
        'cells': [
            {'pos': 0, 'row': 0, 'ch': 0, 'note': 'C-2'},
            {'pos': 1, 'row': 0, 'ch': 0, 'note': 'E-2'},
            {'pos': 3, 'row': 0, 'ch': 0, 'note': 'G-2'},
        ],
        'short_pattern': {'pos': 1, 'lines': 32},
    })


def samples_31_test():
    s = Song(instruments=31)
    p = s.add_pattern()
    for i in range(31):
        s.put(p, i % 4, i * 2, note='C-4', inst=i)
    s.sequence([p])
    s.save('pt_samples_31', {
        'what': 'All 31 sample slots used',
        'expect': 'convert',
        'samples_used': 31,
        'cells': [{'pos': 0, 'row': i * 2, 'ch': i % 4, 'sample': i + 1} for i in range(31)],
    })


def five_tracks_test():
    s = Song(tracks=5)
    p = s.add_pattern()
    for t in range(5):
        s.put(p, t, 0, note='C-4', inst=0)
    s.sequence([p])
    s.save('pt_five_tracks', {
        'what': 'A fifth track is over the limit: refuse, or at least keep the MOD 4-channel',
        'expect': 'refuse_or_4ch',
    })


if __name__ == '__main__':
    for test in (notes_test, note_too_high_test, four_tracks_test, effects_test, structure_test,
                 samples_31_test, five_tracks_test):
        test()
    print('wrote', len([f for f in os.listdir(OUT) if f.endswith('.xrns')]), 'songs to', OUT)
