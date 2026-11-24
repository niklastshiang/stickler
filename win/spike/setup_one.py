"""Sets one adapter up the way the packaged core does (sources copied from the install folder,
uv and its Python in Stickler's own folders) and prints the seconds. Run with the shipped
Python and STICKLER_PACKAGED=windows: `python setup_one.py demucs`."""

import os
import sys
import time

from stickler import api
from stickler_app import paths, setup

os.environ.update(paths.packaged_env())
root = paths.adapters_root()
shipped = paths.adapter_sources()
print(f"sources {shipped} -> {root}", flush=True)
setup.sync_adapters(shipped, root)
started = time.monotonic()
done = api.setup_adapters(sys.argv[1], adapters_root=root)
print(f"setup {done} seconds: {time.monotonic() - started:.1f}")
