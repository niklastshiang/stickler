# Contributing

Stickler is **open source, but not open to outside code**: pull requests from people outside the
project are closed automatically. The code is written by an AI (Claude) and every decision is the
owner's; reviewing outside code is not part of that.

## Welcome: issues

- **Bugs:** what you ran, what happened, and the output of `uv run stickler doctor`.
- **Model suggestions:** an open-source drum separation or transcription model worth testing,
  with a link, its licence and how actively it is maintained.
- **Results on your music:** how Fast or Quality did on songs you know, what went wrong.

Use the [issue forms](../../issues/new/choose). This is a hobby project: there are no guaranteed
response times.

## Not taken

- Model weights, audio, datasets or sheet music in the repository.
- Models without an open licence, cloud services, closed APIs.

## Building on it

The code is under the [MIT license](LICENSE): fork it and change it as you like. How it works:
[CLI guide](docs/cli.md), [benchmark report](docs/report.md), decisions in [`docs/adr/`](docs/adr/).
The rules the code follows are in [`CONSTRAINTS.md`](CONSTRAINTS.md); `scripts/check.sh task`
runs all checks.
