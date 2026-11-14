# Stickler GTK: the music stand

> Idea one-pager, 2026-11-14. Direction chosen by the owner; not yet a spec.

## Problem Statement

How might we take a drummer from "I have a song" to "I have sheet music I trust", without a
terminal, and let them hear whether the notes are right before they practise them?

Target user: other drummers, not technical. They install a Flatpak; setup, model download and
error messages must work without a terminal.

## Recommended Direction

A single-window GTK 4 + libadwaita app (`stickler-gtk`, using only `stickler.api`). Drop a song;
about 15 seconds later the sheet music is shown in the app. The song plays with a marker
following bar by bar, and a switch plays the original, the detected hits, or both. Hearing the
detected hits over the song is how a drummer decides to trust the page.

The sheet is engraved in the app with Verovio (MusicXML → SVG; LGPL, actively maintained: 6.4.0
on PyPI, 2026-10-30; Python bindings), so MuseScore is no longer needed to see the notes. Light
corrections (halve/double tempo, time signature, pickup, simplify, repeats) re-engrave in seconds
from the cache.

v1 knows one pipeline: Fast. Quality comes later as an "improve this result" button that
downloads its models on demand, keeping the first start at ~2.2 GB and free of the Hugging Face
login.

On first start a short setup assistant runs, two screens at most: consent (what is downloaded,
how large, where to, and that the ADTOF weights are for non-commercial use), then the download
with progress, then the empty main window. The analysis shows which step it is in (read audio,
detect hits, find bars, engrave). Setup and analysis share one progress component, and the
consent screen is reused later for the Quality download.

## Key Assumptions to Validate

- [x] Verovio engraves Stickler's drum MusicXML correctly: holds, with two changes on Stickler's
      side (see "Verovio test" below).
- [ ] A bar marker can be driven from `beats`/`downbeats` plus a song-bar → written-bar map
      (Verovio's own timeline is score time, not song time): prototype on a song with repeats.
      Half shown by the test: a bar can be found by its id and marked, and Verovio's timemap
      lists the bars in played order with repeats expanded.
- [ ] Hearing detected hits over the song lets a drummer judge the result in under a minute:
      try it with clicks per class on five songs before choosing samples.
- [ ] `transcribe_song`, `notate` and `setup_adapters` can report progress through a callback
      without changing adapter cache keys (today only `run_benchmark` has one).
- [ ] The model environments can be built on first start inside a Flatpak sandbox: a throwaway
      Flatpak that runs `setup --adapter adtof`.

## Verovio test (2026-11-14)

Verovio 6.4.1 (PyPI) on three songs notated in Fast mode with repeats: Eye of the Tiger
(46 written bars), Chop Suey! (65, with a triplet) and Everlong (119), each compared with the
MuseScore 4 PDF of the same MusicXML. Drawn with librsvg 2.62, as GTK would.

Holds:
- All three load without a warning. Percussion clef, x noteheads, two voices, repeat signs,
  "n×", multi-bar rests, the triplet and the page layout (Eye of the Tiger on one page, as in
  MuseScore) are right.
- Fast enough to re-engrave on every correction: loading ≤ 0.06 s, SVG ≤ 0.05 s per song,
  librsvg ≈ 0.07 s per page.
- Every bar is an SVG group with an id; librsvg returns its rectangle, and a highlight drawn
  over it lands on the bar.
- The timemap (`includeMeasures`) gives the bars in played order, repeats expanded
  (`<id>-rend2`, …): 107 entries for Eye of the Tiger's 110 song bars (the 4-bar rest is one).

Needs work:
- **No beams.** Stickler's MusicXML has no `<beam>` elements; MuseScore beams by itself, Verovio
  draws a flag on every note, which is hard to read. With beams added by a throwaway script
  (one `<beam number="1">` group per beat and voice) the page looks like MuseScore's.
  Done the same day: `notation` writes beams for every reader of the file (owner's decision),
  per beat, with plain eighths joined over half a bar as MuseScore does. MuseScore's PDFs of
  the three songs are pixel-identical to before; in a fourth song (Duality) the beams are
  identical too, and one eighth rest sits about half a staff space higher.
- **Tempo mark.** The note symbol in "♩ = 121" is a missing-glyph box in librsvg: the SVG embeds
  the Leipzig font as `@font-face`, which librsvg ignores. And when the tempo sits in a bar that
  becomes a multi-bar rest (Eye of the Tiger), Verovio drops it and assumes 120. Either ship the
  font with the app, or show the tempo in the window instead.
- **Composer** is not printed (the title is).
- **Bar rectangles** from librsvg are far too large for bars with dotted notes (8 of 43 bars in
  Eye of the Tiger); every `dots` group reports a rectangle reaching the page origin. The bar's
  staff-line coordinates in the SVG would give the rectangle without librsvg.

Not tested: drawing inside a GTK widget, dark mode, narrow windows, Verovio's own PDF path.

## MVP Scope

In:
- Drop or open a song; step display during the analysis.
- Sheet view with a bar marker; playback with original / detected / both.
- Light corrections: halve/double tempo, time signature, pickup, simplify, repeats.
  Tempo, time signature and pickup are new in `stickler.api`; `simplify` and `repeats` exist.
- Export of PDF, MusicXML and the drum track.
- A list of recent songs (free through the cache).
- Setup assistant: consent, download of the Fast models with progress, resumable after an
  interruption.

Out: everything under "Not Doing".

## Not Doing (and Why)

- Quality mode in v1: gated weights, +3.4 GB, about 14 minutes per song; Fast is enough for most
  songs. Later as a button on a finished result.
- Percentage progress inside a model run in v1: Fast takes 15 seconds; it is needed only for
  Quality and requires the adapters to report from their own process.
- Editing single hits: competes with MuseScore; "Open in MuseScore" covers it.
- Practice tools (loop, slow down, mute the stem): a different product; revisit after v1.
- A song library beyond the recent list: scope creep.
- Marking doubtful bars: an idea for the future (owner, 2026-11-14); needs confidence signals
  nobody has measured yet.
- Benchmark, tuning and listening commands in the GUI: developer tools, they stay in the CLI.
- MuseScore as the in-app renderer: a second program to install, and its measure-position export
  (`.mpos`) is reported broken since MuseScore 4.0.
- macOS and Flathub: Linux Flatpak/AppImage from GitHub releases first.

## Open Questions

- Does the PDF export move to Verovio as well, or stay with MuseScore when it is installed?
- Clicks or drum samples for the detected hits (sample licence)?
- How is the SVG shown: librsvg with a drawn overlay (works in the test, see above), or
  WebKitGTK (would honour the embedded font)?
- What does the assistant do when the disk is too small or the download breaks?
- Fallback if Verovio fails the first assumption: a PDF view without a marker, plus the
  listening check.
