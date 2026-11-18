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
SCRIPTS_ALLOWED = {"site.js"}  # the copy button and reduced motion (SPEC "Website")
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
        urls = [(n, attrs.get(n, "")) for n in ("href", "src", "poster")]
        urls += [("srcset", u.split(" ")[0]) for u in re.split(r",\s*", attrs.get("srcset", ""))]
        for name, url in urls:
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


@pytest.mark.parametrize("path", PAGES, ids=lambda p: str(p.relative_to(SITE)))
def test_media_does_not_shift_the_page_and_can_be_stopped(path):
    page = _page(path)
    for attrs in page.all("img"):
        assert attrs.get("width") and attrs.get("height"), attrs  # no layout shift
    for attrs in page.all("video"):
        assert {"controls", "muted", "playsinline", "width", "height"} <= set(attrs), attrs
    for attrs in page.all("audio"):
        assert "controls" in attrs and attrs.get("preload") == "none", attrs


@pytest.mark.parametrize("path", PAGES, ids=lambda p: str(p.relative_to(SITE)))
def test_every_picture_has_a_dark_twin(path):
    """Light and dark follow the browser, pictures and video too (SPEC "Website")."""
    page = _page(path)
    for tag in ("source",):
        for attrs in page.all(tag):
            media = attrs.get("media", "")
            if "prefers-color-scheme: dark" in media:
                url = attrs.get("srcset") or attrs.get("src")
                assert "-dark." in url, url
    darks = [a for a in page.all("source") if "dark" in a.get("media", "")]
    pictures = len(page.all("picture")) + len(page.all("video"))
    assert len(darks) >= pictures, "each picture and video has a dark source"


def test_the_first_view_stays_light():
    """HTML, CSS and the font under 300 KB; with the overview video under 2 MB."""
    text = sum((SITE / f).stat().st_size for f in ("index.html", "style.css", "site.js"))
    font = (SITE / "fonts" / "figtree.woff2").stat().st_size
    assert text + font < 300_000
    assert text + font + (SITE / "images" / "overview.mp4").stat().st_size < 2_000_000


def test_downloads_point_at_the_newest_release_until_the_workflow_fills_them():
    page = _page(SITE / "index.html")
    assets = {a["data-asset"]: a for a in page.all("a") if "data-asset" in a}
    assert set(assets) == {"dmg", "flatpak", "appimage"}
    for attrs in assets.values():
        assert attrs["href"] == "https://github.com/niklastshiang/stickler/releases/latest"
