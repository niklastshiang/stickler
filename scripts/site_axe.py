#!/usr/bin/env python3
"""Runs axe-core on every page of the website, in light and dark (SPEC.md "Website": WCAG 2.2,
level AA). Serves the folder on a local port, opens each page in Playwright's Chromium with the
colour scheme set, injects axe and fails on any violation of WCAG 2.0, 2.1 or 2.2 A/AA.

Usage: uvx --with playwright==<version> python -I scripts/site_axe.py <site dir> <axe.min.js>
       (Chromium for that Playwright: `uvx --from playwright==<version> playwright install
       chromium`). Exit 0 without violations, 1 with them.
"""

from __future__ import annotations

import functools
import http.server
import sys
import threading
from pathlib import Path

TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass


def pages(site: Path) -> list[str]:
    return sorted(str(p.relative_to(site)) for p in site.rglob("*.html"))


def main(argv: list[str]) -> int:
    from playwright.sync_api import sync_playwright

    site, axe = Path(argv[0]).resolve(), Path(argv[1]).read_text(encoding="utf-8")
    handler = functools.partial(Quiet, directory=str(site))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}/"
    found = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for scheme in ("light", "dark"):
            # the pages' CSP allows only their own scripts; axe is injected for the check only
            context = browser.new_context(color_scheme=scheme, bypass_csp=True)
            for name in pages(site):
                page = context.new_page()
                page.goto(base + name)
                page.add_script_tag(content=axe)
                result = page.evaluate(
                    "tags => axe.run(document, {runOnly: {type: 'tag', values: tags}})", TAGS
                )
                for violation in result["violations"]:
                    found += 1
                    targets = [", ".join(n["target"]) for n in violation["nodes"]]
                    print(f"{name} ({scheme}): {violation['id']}: {violation['help']}")
                    for target in targets[:5]:
                        print(f"    {target}")
                for unsure in result["incomplete"]:  # e.g. contrast over a picture: a person looks
                    print(f"{name} ({scheme}): to check by eye: {unsure['id']}: {unsure['help']}")
                print(f"{name} ({scheme}): {len(result['passes'])} rules pass")
                page.close()
            context.close()
        browser.close()
    server.shutdown()
    print(f"site-axe: {found} violation(s)")
    return 1 if found else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
