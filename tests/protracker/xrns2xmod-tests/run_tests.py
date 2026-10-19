#!/usr/bin/env python3
"""Convert every test song with Xrns2XMod and check each MOD.

Usage: run_tests.py <path to Xrns2XModCmd.exe> [songs folder]
On Windows the .exe runs directly; elsewhere it runs under mono.
Converted MODs and logs go in out/. Exits 1 if any song fails.
"""
import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    exe = os.path.abspath(sys.argv[1])
    songs = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'songs')
    out = os.path.join(HERE, 'out')
    os.makedirs(out, exist_ok=True)
    runner = [exe] if os.name == 'nt' else ['mono', exe]
    failed = []
    for e_path in sorted(glob.glob(os.path.join(songs, '*.json'))):
        name = os.path.splitext(os.path.basename(e_path))[0]
        xrns = os.path.join(songs, name + '.xrns')
        mod = os.path.join(out, name + '.mod')
        if os.path.exists(mod):
            os.remove(mod)
        # Hardware mode is the converter's default and what an A1200 needs.
        try:
            r = subprocess.run(runner + [xrns, '-type=mod', '-ptmode=H', '-out=' + mod],
                               capture_output=True, text=True)
        except FileNotFoundError:
            sys.exit("can't run %s (on a Mac or Linux, install mono)" % runner[0])
        open(os.path.join(out, name + '.log'), 'w').write(r.stdout + r.stderr)
        produced = r.returncode == 0 and os.path.exists(mod)
        c = subprocess.run([sys.executable, os.path.join(HERE, 'check_mod.py'), e_path, mod if produced else '-'])
        if c.returncode:
            failed.append(name)
        print()
    print('%d songs, %d failed%s' % (len(glob.glob(os.path.join(songs, '*.json'))), len(failed),
                                     (': ' + ', '.join(failed)) if failed else ''))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
