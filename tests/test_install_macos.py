"""The Mac install guide (SPEC.md, module `mac-package`, scope 6): `docs/install-macos.md` and
the README's install section say what the website's page says, so the three cannot drift."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUIDE = ROOT / "docs" / "install-macos.md"
README = ROOT / "README.md"
PAGE = ROOT / "site" / "install-mac.html"


def _page_steps() -> list[str]:
    html = PAGE.read_text(encoding="utf-8")
    steps = html[html.index('<ol class="steps">') : html.index("</ol>")]
    return re.findall(r"<h3[^>]*>([^<]+)</h3>", steps)


def _page_command() -> str:
    html = PAGE.read_text(encoding="utf-8")
    return re.search(r'<code id="xattr-command">([^<]+)</code>', html).group(1)


def test_the_guide_has_the_pages_steps_in_order():
    guide = GUIDE.read_text(encoding="utf-8")
    steps = re.findall(r"^\d+\. \*\*([^*]+)\*\*", guide, flags=re.M)
    assert _page_steps() == steps[: len(_page_steps())]
    assert len(_page_steps()) == 5


def test_the_guide_and_the_page_give_the_same_terminal_line():
    guide = GUIDE.read_text(encoding="utf-8")
    assert _page_command() in guide
    assert guide.count("xattr") == _page_command().count("xattr"), "one such line, the page's"


def test_the_guide_says_what_the_spec_asks_of_it():
    """Download, drag, Open Anyway, the first start, removing; and what the Mac must be."""
    guide = GUIDE.read_text(encoding="utf-8")
    for needed in (
        ".dmg",
        "Applications",
        "Privacy & Security",
        "Open Anyway",
        "Apple silicon",
        "macOS 26",
        "Remove Downloaded Models…",
        "## The first start",
        "## Removing it",
    ):
        assert needed in guide, needed
    assert "Homebrew" not in guide and "uv " not in guide, "a reader installs nothing else"


def test_the_readme_offers_the_mac_image_and_leads_to_the_guide():
    readme = README.read_text(encoding="utf-8")
    install = readme[readme.index("## `> INSTALL THE APP`") : readme.index("## `> WHY`")]
    assert "docs/install-macos.md" in install
    assert "Stickler-<version>.dmg" in install
    assert "Apple silicon" in install and "macOS 26" in install
    removing = install[install.index("### Removing it") :]
    assert "**Mac:**" in removing and "Remove Downloaded Models…" in removing
    assert "for x86_64 Linux. On first start" not in install, "the Mac is a system too now"
