#!/bin/sh
# Builds the ptplay Shell command. Needs vasmm68k_mot and vlink (http://sun.hasenbraten.de/) on PATH.
set -e
cd "$(dirname "$0")"
mkdir -p build
vasmm68k_mot -quiet -Fhunk -m68020 -DOSCOMPAT=1 -o build/ptplayer.o ptplayer.asm
vasmm68k_mot -quiet -Fhunk -m68020 -o build/ptplay.o ptplay.asm
vlink -bamigahunk -s -o build/ptplay build/ptplay.o build/ptplayer.o
