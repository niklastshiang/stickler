# The bridge protocol

`stickler-bridge` is Stickler's core as one subprocess. The Mac app runs it and talks to it
through JSON lines on stdin and stdout. Python decides what the window shows and translates
every text the reader sees. Swift sends commands and draws the state it gets. This document is
the contract. `tests/app/test_bridge_doc.py` checks it against the code: the commands, the state
kinds and their fields, the events, and that every example decodes.

Source: `src/stickler_app/bridge.py` (the protocol) and `src/stickler_app/controller.py` (the
flows). Specification: SPEC.md, module `core-bridge`.

## Lines and lifetime

- Each line holds one JSON object, in UTF-8. The bridge writes only to stdout, and only these
  lines. Logs, tracebacks and anything a model prints go to stderr.
- The app starts the bridge once per launch and sets `LANGUAGE` to the user's preferred
  languages. Packaged as the Mac app, its launcher also sets `STICKLER_PACKAGED=macos`.
- The first line is `hello`. After it come a `state` event (the empty window) and a `recent`
  event.
- Each command is `{"id": <int>, "cmd": "<name>", ...arguments}`. It gets exactly one reply,
  The bridge handles commands one at a time. Most reply at once; `pages`, `a4_pages` and
  `removal_sizes` take a moment (engraving, walking folders), and the commands after them,
  `cancel` too, wait for it. Long work, such as an analysis or a download, is reported through
  `state` events.
- Paths in commands should be absolute; a relative one is read from the bridge's working
  directory.
- Events and replies can interleave. The events a command causes are sent before its reply.
- `quit`, or stdin closing, cancels the running job. The bridge then waits at most 2 s for the
  job's clean-up and exits with status 0.

Replies:

```json
{"id": 4, "ok": true}
{"id": 5, "ok": false, "error": {"code": "not_now", "message": "This is not possible right now."}}
```

## Errors

| Code | When |
|---|---|
| `bad_request` | The line is not a JSON object with an integer `id` and a string `cmd`. The reply's `id` is `null` when none could be read. |
| `unknown_command` | No command has this name. |
| `bad_argument` | An argument is missing or has the wrong type or value. The message names it. |
| `not_now` | The command does not fit the state, e.g. `export_musicxml` without a result. |
| `internal` | The command failed for a reason nobody foresaw (a bug). The traceback goes to stderr, and the bridge keeps running. |

The `message` is translated and can be shown as it is. A failure inside a flow is not an
error reply: it becomes a `failed` or `setup_failed` state.

## Events

Every event except `hello` has a `seq` that grows by one per event, so the app can tell the
order and drop a late one. Unsent `state` events are dropped when the app does not read: only
the newest 64 are kept. Each state is whole, so the newest is enough. No reply and no other
event is ever dropped.

### `hello`

The first line. `language` is the catalogue found, `en` without one.

```json
{"event": "hello", "protocol": 1, "version": "7", "language": "de"}
```

### `state`

After every change, the whole state: see [States](#states). The SVG pages are not part of it
(see `pages`).

```json
{"event": "state", "seq": 1, "state": {"kind": "empty", "can_open": true, "can_cancel": false, "can_retry": false, "can_close": false, "can_export": false, "can_agree": false, "can_not_now": false, "can_retry_setup": false, "can_remove_models": false}}
```

### `recent`

The recent songs, newest first, at most 10. It comes at the start and whenever the list
changes. `missing` means the file is gone, so the row can only be removed (`forget_recent`).

```json
{"event": "recent", "seq": 2, "rows": [{"path": "/Users/me/Music/Eye of the Tiger.flac", "title": "Eye of the Tiger", "detail": "Survivor · opened today", "missing": false}]}
```

### `notice`

A short message the GTK app shows as a toast; the state stays as it is. `opens` names a file
that was just saved, so the app can offer to open it; otherwise it is `null`.

```json
{"event": "notice", "seq": 9, "text": "Saved “Eye of the Tiger.musicxml”", "opens": "/Users/me/Desktop/Eye of the Tiger.musicxml"}
```

## States

Every state has `kind` and the `can_*` fields below. The app enables its buttons and menu
items from these alone.

| Field | True when |
|---|---|
| `can_open` | Always: a new song cancels what runs. |
| `can_cancel` | Something runs: `analysing`, `exporting`, `setting_up`. |
| `can_retry` | A `failed` analysis can be tried again. |
| `can_close` | The window shows anything but `empty`. |
| `can_export` | There is a `result`. |
| `can_agree` | The `consent` asks. |
| `can_not_now` | The `consent` asks, or a download failed. |
| `can_retry_setup` | A download failed. |
| `can_remove_models` | The app is installed and nothing runs (`remove_models`). |

A step row has `id` (stable, not translated), `label`, `detail` and `state` (`waiting`,
`running` or `done`). Paths are absolute strings. `song` is `null` when no song waits.

### `empty`

The window to drop a song on.

```json
{"kind": "empty", "can_open": true, "can_cancel": false, "can_retry": false, "can_close": false, "can_export": false, "can_agree": false, "can_not_now": false, "can_retry_setup": false, "can_remove_models": false}
```

### `consent`

May the models be downloaded? (design screen 1). `models` lists each missing model: what it
does, its licence and its size. `song` is opened once the models are there.

```json
{"kind": "consent", "song": null, "models": [{"id": "adtof", "name": "ADTOF", "does": "detects the hits", "licence": "Its trained model is free for non-commercial use only (CC BY-NC-SA 4.0).", "size": "1.3 GB"}, {"id": "beat_this", "name": "Beat This!", "does": "finds the beat and the bars", "licence": "MIT licence. Its model comes from the JKU Linz server.", "size": "0.9 GB"}], "total_size": "2.2 GB", "can_open": true, "can_cancel": false, "can_retry": false, "can_close": true, "can_export": false, "can_agree": true, "can_not_now": true, "can_retry_setup": false, "can_remove_models": false}
```

### `setting_up`

The models are being downloaded (design screen 2). About twice a second, the running step's
`detail` says how much it has downloaded.

```json
{"kind": "setting_up", "song": null, "steps": [{"id": "environment:adtof", "label": "Download the programs for ADTOF", "detail": "650 MB of 1.3 GB", "state": "running"}, {"id": "weights:beat_this", "label": "Download the Beat This! model", "detail": "Once; later songs use it too", "state": "waiting"}], "can_open": true, "can_cancel": true, "can_retry": false, "can_close": true, "can_export": false, "can_agree": false, "can_not_now": false, "can_retry_setup": false, "can_remove_models": false}
```

### `setup_failed`

A download did not work (design screen 3). What finished stays done. `step` is the step that
failed, `server` names who did not answer, and `details` holds the error's last lines.

```json
{"kind": "setup_failed", "song": null, "steps": [{"id": "weights:beat_this", "label": "Download the Beat This! model", "detail": "Once; later songs use it too", "state": "running"}], "step": "weights:beat_this", "server": "JKU Linz (cloud.cp.jku.at) and Stickler’s copy (github.com)", "details": "Beat This! model not downloaded. JKU Linz: 500", "can_open": true, "can_cancel": false, "can_retry": false, "can_close": true, "can_export": false, "can_agree": false, "can_not_now": true, "can_retry_setup": true, "can_remove_models": false}
```

### `analysing`

A song is being written as sheet music. `name` is the file's name, shown until the result has
the title.

```json
{"kind": "analysing", "song": "/Users/me/Music/Eye of the Tiger.flac", "name": "Eye of the Tiger", "steps": [{"id": "transcribe", "label": "Detect the hits", "detail": "Kick, snare, toms, hi-hat, cymbals", "state": "done"}, {"id": "beats", "label": "Find the beat and the bars", "detail": "Tempo, time signature, the first “one”", "state": "running"}, {"id": "engrave", "label": "Write the notes", "detail": "Bars, repeats, beams", "state": "waiting"}], "can_open": true, "can_cancel": true, "can_retry": false, "can_close": true, "can_export": false, "can_agree": false, "can_not_now": false, "can_retry_setup": false, "can_remove_models": false}
```

### `result`

The sheet music. `subtitle` is the header's second line. `corrections` are the values the
corrections controls show, and `correcting` is true while a correction is being notated. Both
are for `mac-corrections`. The pages come from `pages`.

```json
{"kind": "result", "song": "/Users/me/Music/Eye of the Tiger.flac", "title": "Eye of the Tiger", "subtitle": "Survivor · ♩ = 109 · 4/4", "artist": "Survivor", "seconds": 246.0, "tempo": 109, "meter": [4, 4], "musicxml": "/Users/me/Library/Caches/Stickler/scores/Eye of the Tiger-1a2b3c4d5e.musicxml", "corrections": {"tempo": "normal", "beats_per_bar": null, "first_downbeat": null, "simplify": true, "repeats": true}, "correcting": false, "can_open": true, "can_cancel": false, "can_retry": false, "can_close": true, "can_export": true, "can_agree": false, "can_not_now": false, "can_retry_setup": false, "can_remove_models": false}
```

### `exporting`

The drum track is being separated and saved. Cancelling goes back to the result. The header
keeps the result's `title` and `subtitle`.

```json
{"kind": "exporting", "song": "/Users/me/Music/Eye of the Tiger.flac", "title": "Eye of the Tiger", "subtitle": "Survivor · ♩ = 109 · 4/4", "dest": "/Users/me/Desktop/Eye of the Tiger (drums).flac", "steps": [{"id": "separate", "label": "Separate the drums", "detail": "Only the drum track, without the band", "state": "running"}], "can_open": true, "can_cancel": true, "can_retry": false, "can_close": true, "can_export": false, "can_agree": false, "can_not_now": false, "can_retry_setup": false, "can_remove_models": false}
```

### `failed`

Something went wrong with a song. `reason` is `unreadable` (not a sound file), `analysis` (can
be tried again) or `export`. `details` holds the technical message, for "Technical Details".

```json
{"kind": "failed", "song": "/Users/me/Music/Eye of the Tiger.flac", "name": "Eye of the Tiger", "reason": "analysis", "title": "The Analysis Failed", "description": "Something went wrong while listening to “Eye of the Tiger.flac”.", "details": "adtof (exit 1): out of memory", "can_open": true, "can_cancel": false, "can_retry": true, "can_close": true, "can_export": false, "can_agree": false, "can_not_now": false, "can_retry_setup": false, "can_remove_models": false}
```

## Commands

Each example shows the command and then its reply. A command that does not fit the state gets
`not_now`.

### `start`

The model check at launch: it leads to `empty` (all there), `consent` or, if the download was
agreed to before and interrupted, `setting_up`. A packaged app first refreshes its models'
sources.

```json
{"id": 1, "cmd": "start"}
{"id": 1, "ok": true}
```

### `agree`

On `consent`: the download starts, and the answer is remembered.

```json
{"id": 2, "cmd": "agree"}
{"id": 2, "ok": true}
```

### `not_now`

"Not Now" on `consent`, or "Later" on `setup_failed`: back to `empty`.

```json
{"id": 3, "cmd": "not_now"}
{"id": 3, "ok": true}
```

### `retry_setup`

On `setup_failed`: the download goes on from the step that failed.

```json
{"id": 4, "cmd": "retry_setup"}
{"id": 4, "ok": true}
```

### `open`

Analyses the song at `path` with its stored corrections. Anything running is cancelled. Missing
models lead to `consent`, and the song is opened after the download.

```json
{"id": 5, "cmd": "open", "path": "/Users/me/Music/Eye of the Tiger.flac"}
{"id": 5, "ok": true}
```

### `cancel`

Stops what runs and goes back to where it started: an analysis to the previous state, an
export to the result, a download to `empty`.

```json
{"id": 6, "cmd": "cancel"}
{"id": 6, "ok": true}
```

### `retry`

On a `failed` analysis: analyses the song again.

```json
{"id": 7, "cmd": "retry"}
{"id": 7, "ok": true}
```

### `close`

Back to `empty`; anything running is cancelled.

```json
{"id": 8, "cmd": "close"}
{"id": 8, "ok": true}
```

### `pages`

The result's sheet music, `width` pixels wide, one long page per screen width. `zoom` makes
the notes larger at the same width. It defaults to the stored note size and is clamped to 0.5
to 3. Each page is an SVG with its size, plus the written bars' rectangles in page pixels, top
to bottom: a click on one jumps there. The SVG strings are long (a whole song).

```json
{"id": 9, "cmd": "pages", "width": 800, "zoom": 1.25}
{"id": 9, "ok": true, "zoom": 1.25, "pages": [{"svg": "<svg width=\"800px\" height=\"252px\" …</svg>", "width": 800.0, "height": 252.0, "bars": [{"bar": 1, "x": 111.85, "y": 37.85, "width": 198.5, "height": 72.0}, {"bar": 2, "x": 310.35, "y": 37.85, "width": 154.9, "height": 72.0}]}]}
```

### `a4_pages`

The result's A4 pages, for the PDF the app writes: each page's size is A4 in its proportions
(1050 × 1485), to be scaled to 210 × 297 mm. `title` is the PDF's title.

```json
{"id": 10, "cmd": "a4_pages"}
{"id": 10, "ok": true, "title": "Eye of the Tiger", "pages": [{"svg": "<svg …</svg>", "width": 1050.0, "height": 1485.0, "bars": [{"bar": 1, "x": 111.85, "y": 64.65, "width": 217.55, "height": 72.0}]}]}
```

### `export_musicxml`

Copies the result's MusicXML to `dest`. A `notice` follows: "Saved …" with `opens`, or why it
could not be saved.

```json
{"id": 11, "cmd": "export_musicxml", "dest": "/Users/me/Desktop/Eye of the Tiger.musicxml"}
{"id": 11, "ok": true}
```

### `drum_track_cost`

What saving the drum track would cost, to say before it starts. `download` is true when Demucs
is downloaded first.

```json
{"id": 12, "cmd": "drum_track_cost"}
{"id": 12, "ok": true, "minutes": 8, "text": "Separating the drums takes about 8 minutes on this computer. Before that, Demucs is downloaded once (about 1.2 GB).", "download": true}
```

### `export_drum_track`

Separates the drums and saves them at `dest` (FLAC, WAV, OGG or MP3 by its suffix). It shows
`exporting`, then goes back to the result with a `notice`.

```json
{"id": 13, "cmd": "export_drum_track", "dest": "/Users/me/Desktop/Eye of the Tiger (drums).flac"}
{"id": 13, "ok": true}
```

### `forget_recent`

Removes a song from the recent songs. A `recent` event follows.

```json
{"id": 14, "cmd": "forget_recent", "path": "/Users/me/Music/Gone.flac"}
{"id": 14, "ok": true}
```

### `settings`

The stored settings, with the note size as the menu shows it.

```json
{"id": 15, "cmd": "settings"}
{"id": 15, "ok": true, "appearance": "system", "zoom": 1.0, "song_volume": 0.7, "hits_volume": 1.0, "setup_agreed": true, "percent": "100%"}
```

### `set_zoom`

Sets the note size for every song (clamped to 0.5 to 3) and remembers it. The reply has the new
size. Fetch `pages` again after it.

```json
{"id": 16, "cmd": "set_zoom", "zoom": 1.5}
{"id": 16, "ok": true, "zoom": 1.5, "percent": "150%"}
```

### `zoom_in`

One step larger (×1.25).

```json
{"id": 17, "cmd": "zoom_in"}
{"id": 17, "ok": true, "zoom": 1.25, "percent": "125%"}
```

### `zoom_out`

One step smaller (÷1.25).

```json
{"id": 18, "cmd": "zoom_out"}
{"id": 18, "ok": true, "zoom": 0.8, "percent": "80%"}
```

### `actual_size`

Back to the window's width (1.0).

```json
{"id": 19, "cmd": "actual_size"}
{"id": 19, "ok": true, "zoom": 1.0, "percent": "100%"}
```

### `removal_sizes`

What "Remove Downloaded Models…" would free, in bytes and as the dialog's text: the models
alone, or everything (settings, recent songs and corrections too). It walks the folders, so the
reply can take a moment.

```json
{"id": 20, "cmd": "removal_sizes"}
{"id": 20, "ok": true, "models": 2213000000, "everything": 2213400000, "models_text": "This frees 2.2 GB. Stickler asks before it downloads the models again.", "everything_text": "This frees 2.2 GB. Stickler asks before it downloads the models again."}
```

### `remove_models`

Removes the downloaded models. With `everything`, the settings, recent songs and corrections go
too. Only in an installed app, and not while something runs (`can_remove_models`). A `notice`
follows when it is done.

```json
{"id": 21, "cmd": "remove_models", "everything": false}
{"id": 21, "ok": true}
```

### `quit`

Cancels what runs, waits at most 2 s for its clean-up and exits 0. The reply comes first; a
`state` event of the cancelled job can still follow it.

```json
{"id": 22, "cmd": "quit"}
{"id": 22, "ok": true}
```
