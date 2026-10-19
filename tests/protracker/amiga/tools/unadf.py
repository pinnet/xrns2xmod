#!/usr/bin/env python3
"""Extract an Amiga OFS/FFS floppy image (.adf) into a folder. Read-only on the image.

Usage: python unadf.py <disk.adf> <out_dir>
Amiga protection bits and file comments are not kept: files come out with the
default RWED bits, which is fine for a Workbench boot volume (scripts are run
with Execute).
"""
import os
import struct
import sys

BS = 512


def longs(b):
    return struct.unpack('>128l', b)


def name_of(b):
    n = b[432]
    return b[433:433 + n].decode('latin-1')


def read_file(img, hdr, ffs):
    data = bytearray()
    size = struct.unpack('>L', hdr[324:328])[0]
    block = hdr
    while True:
        L = longs(block)
        count = L[2]
        for i in range(count):
            ptr = L[77 - i]
            d = img[ptr * BS:(ptr + 1) * BS]
            data += d if ffs else d[24:24 + struct.unpack('>L', d[12:16])[0]]
        ext = L[126]
        if not ext:
            break
        block = img[ext * BS:(ext + 1) * BS]
    return bytes(data[:size])


def walk(img, block_no, out, ffs, prefix=''):
    b = img[block_no * BS:(block_no + 1) * BS]
    L = longs(b)
    for h in L[6:78]:
        while h:
            e = img[h * BS:(h + 1) * BS]
            E = longs(e)
            name = name_of(e)
            sec = E[127]
            path = os.path.join(out, name)
            if sec == 2:                       # ST_USERDIR
                os.makedirs(path, exist_ok=True)
                yield prefix + name + '/'
                yield from walk(img, h, path, ffs, prefix + name + '/')
            elif sec == -3:                    # ST_FILE
                with open(path, 'wb') as f:
                    f.write(read_file(img, e, ffs))
                yield prefix + name
            h = E[124]                         # hash chain


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    img = open(sys.argv[1], 'rb').read()
    if img[:3] != b'DOS':
        sys.exit('not an AmigaDOS disk')
    ffs = img[3] & 1
    root = len(img) // BS // 2
    os.makedirs(sys.argv[2], exist_ok=True)
    n = 0
    for p in walk(img, root, sys.argv[2], ffs):
        n += 1
    print('%s: %s, %d entries extracted to %s' % (name_of(img[root * BS:(root + 1) * BS]), 'FFS' if ffs else 'OFS', n, sys.argv[2]))


if __name__ == '__main__':
    main()
