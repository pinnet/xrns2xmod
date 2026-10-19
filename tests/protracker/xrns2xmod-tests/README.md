# Xrns2XMod tests

Checks that Xrns2XMod turns a Renoise song into a MOD that ptplayer can play on a stock A1200. We write music within ProTracker's limits, so the tests cover only that subset: 4 tracks, notes C-1 to A-3, up to 31 samples, ProTracker effects.

## Files

- `songs/*.xrns`: seven small test songs. Each has a `.json` beside it saying what the MOD must contain.
- `run_tests.py`: converts every song and checks every MOD.
- `check_mod.py`: checks one MOD against ProTracker's limits and the song's expectations.
- `make_test_songs.py`: rebuilds `songs/` from an xrns2xmod checkout (it borrows the repo's empty song and test instruments).
- `resave_in_renoise.lua`: optional Renoise script that re-saves all the songs for you.
- `selftest.py`: proves the checker works by feeding it ideal MODs (must pass) and broken ones (must fail). No converter needed.
- `modfile.py`: reads and writes MOD files.

## The songs

| Song | Expect | Tests |
|---|---|---|
| pt_notes | convert | Renoise C-3 upwards comes out as C-1 to A-3, a semitone per row |
| pt_note_too_high | convert | B-5 is above A-3: the converter reports an error and must drop the note |
| pt_four_tracks | convert | One note per track, each with its own sample |
| pt_effects | convert | Arpeggio, vibrato, slides, tone portamento, volume column, volume slide, sample offset, retrigger, note delay, note off, speed, tempo, pattern break |
| pt_structure | convert | Sequence 0,1,0,2 with a 32-line pattern, which must end in a pattern break |
| pt_samples_31 | convert | All 31 sample slots |
| pt_five_tracks | refuse or 4ch | A fifth track must never produce a 6- or 8-channel MOD |

Every converted MOD is also checked for: M.K. signature, at most 64 patterns, samples under 128 KB, loops inside their samples, volumes 0-64, no missing sample data, no E8x, no F00, and no notes played on empty samples.

## Running them

You need Python 3 and a built Xrns2XModCmd.exe (Windows, or mono on a Mac).

1. Re-save the songs in your Renoise so they carry its format, as the converter will see in real use. Either open and save each one by hand, or run `resave_in_renoise.lua` from Renoise's script editor (set the `SONGS` path at the top first; it is untested). Leave the notes alone.
2. Run `python run_tests.py path\to\Xrns2XModCmd.exe`.
3. Each song prints PASS or FAIL per check. MODs and converter logs land in `out/`.

`python selftest.py` checks the checker. It should print `selftest: all good`.

Expected values come from reading Xrns2XMod's source (`ModCommands.cs`, `ModUtils.cs`). They have not yet been seen against the real converter, so a first-run failure may mean a wrong expectation rather than a converter bug. Check which before fixing.
