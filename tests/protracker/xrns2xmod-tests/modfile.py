"""Read (and, for the self-test, write) 4-channel ProTracker MOD files."""
import struct

# ProTracker's period table at finetune 0: C-1 to B-3.
PERIODS = [856, 808, 762, 720, 678, 640, 604, 570, 538, 508, 480, 453,
           428, 404, 381, 360, 339, 320, 302, 285, 269, 254, 240, 226,
           214, 202, 190, 180, 170, 160, 151, 143, 135, 127, 120, 113]
NAMES = ['C-', 'C#', 'D-', 'D#', 'E-', 'F-', 'F#', 'G-', 'G#', 'A-', 'A#', 'B-']


def note_name(period):
    if period == 0:
        return '---'
    if period in PERIODS:
        i = PERIODS.index(period)
        return '%s%d' % (NAMES[i % 12], i // 12 + 1)
    return '?%d' % period


class Sample:
    def __init__(self, name, length, finetune, volume, loop_start, loop_length, data=b''):
        self.name, self.length, self.finetune, self.volume = name, length, finetune, volume
        self.loop_start, self.loop_length, self.data = loop_start, loop_length, data


class Cell:
    def __init__(self, sample=0, period=0, effect=0, param=0):
        self.sample, self.period, self.effect, self.param = sample, period, effect, param

    def __repr__(self):
        return '%s %02d %X%02X' % (note_name(self.period), self.sample, self.effect, self.param)


class Mod:
    def __init__(self):
        self.title = ''
        self.samples = []      # 31 Sample objects (index 0 is sample 1)
        self.order = []        # the song's positions
        self.restart = 0
        self.signature = 'M.K.'
        self.patterns = []     # each: 64 rows of 4 Cells
        self.order_table = []  # all 128 entries as stored

    def cell(self, position, row, channel):
        return self.patterns[self.order[position]][row][channel]


def read(path):
    data = open(path, 'rb').read()
    m = Mod()
    m.title = data[0:20].rstrip(b'\0').decode('latin-1')
    p = 20
    for _ in range(31):
        name, length, ft, vol, ls, ll = struct.unpack('>22sHBBHH', data[p:p + 30])
        ft = ft & 15
        m.samples.append(Sample(name.rstrip(b'\0').decode('latin-1'), length * 2, ft - 16 if ft > 7 else ft,
                                vol, ls * 2, ll * 2))
        p += 30
    song_length, m.restart = data[p], data[p + 1]
    m.order_table = list(data[p + 2:p + 130])
    m.order = m.order_table[:song_length]
    m.signature = data[p + 130:p + 134].decode('latin-1')
    p += 134
    channels = 4 if m.signature in ('M.K.', 'M!K!', 'FLT4', '4CHN') else None
    if channels is None:
        raise ValueError('not a 4-channel ProTracker MOD (signature %r)' % m.signature)
    # ProTracker counts patterns over the whole 128-entry table.
    count = max(m.order_table) + 1
    for _ in range(count):
        rows = []
        for _ in range(64):
            row = []
            for _ in range(4):
                b0, b1, b2, b3 = data[p:p + 4]
                row.append(Cell((b0 & 0xF0) | (b2 >> 4), ((b0 & 15) << 8) | b1, b2 & 15, b3))
                p += 4
            rows.append(row)
        m.patterns.append(rows)
    for s in m.samples:
        s.data = data[p:p + s.length]
        p += s.length
    m.trailing = len(data) - p
    return m


def write(path, m):
    out = bytearray(m.title.encode('latin-1')[:20].ljust(20, b'\0'))
    for s in m.samples + [Sample('', 0, 0, 0, 0, 2)] * (31 - len(m.samples)):
        out += struct.pack('>22sHBBHH', s.name.encode('latin-1')[:22], s.length // 2, s.finetune & 15,
                           s.volume, s.loop_start // 2, max(1, s.loop_length // 2))
    table = (m.order + [0] * 128)[:128]
    out += bytes([len(m.order), m.restart]) + bytes(table) + m.signature.encode('latin-1')
    for pat in m.patterns:
        for row in pat:
            for c in row:
                out += bytes([(c.sample & 0xF0) | (c.period >> 8), c.period & 255,
                              ((c.sample & 15) << 4) | c.effect, c.param])
    for s in m.samples:
        out += s.data
    open(path, 'wb').write(out)
