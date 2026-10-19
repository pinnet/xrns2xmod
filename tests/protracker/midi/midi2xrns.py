#!/usr/bin/env python3
"""Turn a short MIDI file into a ProTracker-safe Renoise song (.xrns) for xrns2xmod.

The MOD has 4 channels, so notes are spread over at most 4 monophonic voices
(highest notes first), quantised to 4 lines per beat, and shifted by whole
octaves into ProTracker's A1200-safe range (Renoise C-3 to A-5, MOD C-1 to A-3).
Each voice gets its own simple waveform so the parts are easy to tell apart.

Usage: python midi2xrns.py <song.mid> <out.xrns> [xrns2xmod checkout]
"""
import os
import struct
import sys

LPB = 4                 # Renoise lines per beat in xrns2xmod's MOD template
LOW, HIGH = 36, 69      # Renoise C-3 .. A-5
VOICES = 4
ROWS = 64


def read_midi(path):
    data = open(path, 'rb').read()
    if data[:4] != b'MThd':
        sys.exit('not a MIDI file')
    _, ntracks, division = struct.unpack('>HHH', data[8:14])
    if division & 0x8000:
        sys.exit('SMPTE time division is not supported')
    pos, notes, tempo = 14, [], None
    for t in range(ntracks):
        if data[pos:pos + 4] != b'MTrk':
            sys.exit('bad track chunk')
        length = struct.unpack('>I', data[pos + 4:pos + 8])[0]
        p, end, tick, status, on = pos + 8, pos + 8 + length, 0, 0, {}
        pos = end
        while p < end:
            delta = 0
            while True:
                b = data[p]; p += 1
                delta = (delta << 7) | (b & 0x7f)
                if not b & 0x80:
                    break
            tick += delta
            if data[p] & 0x80:
                status = data[p]; p += 1
            kind = status & 0xf0
            if status == 0xff:
                meta = data[p]; p += 1
                n = 0
                while True:
                    b = data[p]; p += 1
                    n = (n << 7) | (b & 0x7f)
                    if not b & 0x80:
                        break
                if meta == 0x51 and tempo is None:
                    tempo = int.from_bytes(data[p:p + 3], 'big')
                p += n
            elif status in (0xf0, 0xf7):
                n = 0
                while True:
                    b = data[p]; p += 1
                    n = (n << 7) | (b & 0x7f)
                    if not b & 0x80:
                        break
                p += n
            elif kind in (0x80, 0x90):
                key, vel = data[p], data[p + 1]; p += 2
                ch = status & 0x0f
                if kind == 0x90 and vel:
                    on[(ch, key)] = tick
                elif (ch, key) in on:
                    start = on.pop((ch, key))
                    if ch != 9:          # skip General MIDI drums
                        notes.append((start, tick, key, t))
            elif kind in (0xc0, 0xd0):
                p += 1
            else:
                p += 2
    return division, tempo or 500000, sorted(notes, key=lambda n: (n[0], -n[2]))


def octave_shift(keys):
    """Whole-octave shift that puts most notes inside LOW..HIGH (Renoise = MIDI - 12)."""
    best = None
    for shift in range(-48, 49, 12):
        inside = sum(LOW <= k - 12 + shift <= HIGH for k in keys)
        score = (inside, -abs(shift))
        if best is None or score > best[0]:
            best = (score, shift)
    return best[1]


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    midi, out = sys.argv[1], sys.argv[2]
    src = sys.argv[3] if len(sys.argv) > 3 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')
    kit = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'xrns2xmod-tests')
    sys.argv = [sys.argv[0], src, os.path.dirname(os.path.abspath(out))]
    sys.path.insert(0, kit)
    import make_test_songs as mts

    division, tempo, notes = read_midi(midi)
    ticks_per_row = division / LPB
    shift = octave_shift([n[2] for n in notes])
    voices = [[] for _ in range(VOICES)]   # each: list of (row, end_row, renoise_note)
    dropped = 0
    for start, end, key, _ in notes:
        row = round(start / ticks_per_row)
        end_row = max(row + 1, round(end / ticks_per_row))
        note = key - 12 + shift
        while note > HIGH:
            note -= 12
        while note < LOW:
            note += 12
        free = [v for v in voices if not v or v[-1][1] <= row]
        free.sort(key=lambda v: abs(v[-1][2] - note) if v else 99)   # keep each part on one voice
        if not free:
            dropped += 1
            continue
        free[0].append((row, end_row, note))

    length = max((v[-1][1] for v in voices if v), default=1)
    npat = (length + ROWS - 1) // ROWS
    if npat > 64:
        sys.exit('song too long for a MOD (%d patterns)' % npat)
    song = mts.Song(instruments=VOICES)
    pats = [song.add_pattern() for _ in range(npat)]
    bpm = round(60000000 / tempo)
    song.put(pats[0], 'master', 0, fx=('ZT', '%02X' % max(32, min(255, bpm))))
    for vi, voice in enumerate(voices):
        for i, (row, end_row, note) in enumerate(voice):
            song.put(pats[row // ROWS], vi, row % ROWS, note=note, inst=vi)
            nxt = voice[i + 1][0] if i + 1 < len(voice) else None
            if (nxt is None or end_row < nxt) and end_row < npat * ROWS:
                song.put(pats[end_row // ROWS], vi, end_row % ROWS, note='OFF')
    song.sequence(pats)
    name = os.path.splitext(os.path.basename(out))[0]
    song.save(name, {'what': 'converted from ' + os.path.basename(midi), 'expect': 'convert'})
    os.remove(os.path.join(os.path.dirname(os.path.abspath(out)), name + '.json'))
    print('%s: %d notes, %d voices used, %d dropped (more than 4 at once), %d patterns, %d BPM, shifted %+d semitones'
          % (name, len(notes) - dropped, sum(1 for v in voices if v), dropped, npat, bpm, shift))


if __name__ == '__main__':
    main()
