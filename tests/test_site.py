"""The website in site/ (SPEC.md "Website"): plain HTML and CSS that never reaches another
server, links that resolve, and the structure WCAG 2.2 AA needs."""

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import pytest

SITE = Path(__file__).resolve().parents[1] / "site"
PAGES = sorted(SITE.rglob("*.html"))
STYLES = sorted(SITE.rglob("*.css"))
SCRIPTS_ALLOWED = {"copy.js"}  # the copy button (SPEC "Website": the only script)
# attributes that load something into the page (a link to elsewhere does not load anything)
LOADING = {"src", "srcset", "poster", "data"}


class Page(HTMLParser):
    def __init__(self, path: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.path = path
        self.tags: list[tuple[str, dict[str, str]]] = []
        self.ids: set[str] = set()
        self.headings: list[int] = []
        self.inline_scripts = 0
        self._in_script = False
        self.feed(path.read_text(encoding="utf-8"))

    def handle_starttag(self, tag, attrs):
        values = {k: v or "" for k, v in attrs}
        self.tags.append((tag, values))
        if "id" in values:
            self.ids.add(values["id"])
        if re.fullmatch(r"h[1-6]", tag):
            self.headings.append(int(tag[1]))
        if tag == "script" and "src" not in values:
            self._in_script = True

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_script = False

    def handle_data(self, data):
        if self._in_script and data.strip():
            self.inline_scripts += 1

    def all(self, tag: str) -> list[dict[str, str]]:
        return [a for t, a in self.tags if t == tag]


def _page(path: Path) -> Page:
    return Page(path)


def _local(url: str) -> bool:
    parts = urlsplit(url)
    return not parts.scheme and not parts.netloc


def _resolve(page: Path, url: str) -> tuple[Path, str]:
    """The file and the fragment a local URL points to."""
    parts = urlsplit(url)
    if not parts.path:
        return page, parts.fragment
    root = SITE if parts.path.startswith("/") else page.parent
    target = root / parts.path.lstrip("/")
    if target.is_dir() or parts.path.endswith("/"):
        target = target / "index.html"
    return target.resolve(), parts.fragment


def test_the_site_has_pages():
    assert (SITE / "index.html") in PAGES


@pytest.mark.parametrize("path", PAGES, ids=lambda p: str(p.relative_to(SITE)))
def test_every_local_link_and_anchor_resolves(path):
    page = _page(path)
    for _tag, attrs in page.tags:
        for name in ("href", "src", "poster"):
            url = attrs.get(name, "")
            if not url or not _local(url) or url.startswith("mailto:"):
                continue
            target, fragment = _resolve(path, url)
            assert target.is_file(), f"{name}={url!r} → {target}"
            if fragment:
                ids = page.ids if target == path else _page(target).ids
                assert fragment in ids, f"{url!r}: no id {fragment!r}"


@pytest.mark.parametrize("path", PAGES, ids=lambda p: str(p.relative_to(SITE)))
def test_nothing_is_loaded_from_another_server(path):
    page = _page(path)
    for tag, attrs in page.tags:
        loads = {k: v for k, v in attrs.items() if k in LOADING}
        if tag == "link" and attrs.get("rel", "") not in ("alternate", "canonical"):
            loads["href"] = attrs.get("href", "")
        for name, url in loads.items():
            for one in re.split(r",\s*", url):
                assert _local(one.split(" ")[0]), f"<{tag} {name}={url!r}>"


@pytest.mark.parametrize("path", STYLES, ids=lambda p: str(p.relative_to(SITE)))
def test_styles_load_nothing_from_another_server(path):
    css = path.read_text(encoding="utf-8")
    assert "@import" not in css
    for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", css):
        assert _local(url), url
        assert (path.parent / url).is_file(), url


@pytest.mark.parametrize("path", PAGES, ids=lambda p: str(p.relative_to(SITE)))
def test_only_the_allowed_script_runs(path):
    page = _page(path)
    assert page.inline_scripts == 0
    for attrs in page.all("script"):
        assert Path(urlsplit(attrs["src"]).path).name in SCRIPTS_ALLOWED, attrs["src"]
    for _tag, attrs in page.tags:
        assert not [k for k in attrs if k.startswith("on")], attrs  # no inline handlers


@pytest.mark.parametrize("path", PAGES, ids=lambda p: str(p.relative_to(SITE)))
def test_the_structure_a_screen_reader_needs(path):
    page = _page(path)
    (html,) = page.all("html")
    assert html.get("lang") in ("en", "de")
    assert len(page.all("main")) == 1 and page.all("main")[0].get("id") == "content"
    assert len(page.all("h1")) == 1
    for before, after in zip(page.headings, page.headings[1:], strict=False):
        assert after <= before + 1, f"h{before} → h{after}"
    first_link = page.all("a")[0]
    assert first_link.get("href") == "#content" and "skip" in first_link.get("class", "")
    for attrs in page.all("img"):
        assert "alt" in attrs, attrs
    for attrs in page.all("nav"):
        assert attrs.get("aria-label"), "every nav is named"
    assert page.all("meta") and any(m.get("name") == "viewport" for m in page.all("meta"))
