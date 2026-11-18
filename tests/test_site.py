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


@pytest.mark.parametrize("path", PAGES, ids=lambda p: str(p.relative_to(SITE)))
def test_the_first_view_stays_light(path):
    """HTML, CSS and the font under 300 KB; with the overview video under 2 MB."""
    shared = sum((SITE / f).stat().st_size for f in ("style.css", "site.js", "fonts/figtree.woff2"))
    assert path.stat().st_size + shared < 300_000
    video = max((SITE / "images").glob("overview*.*"), key=lambda v: v.stat().st_size)
    assert path.stat().st_size + shared + video.stat().st_size < 2_000_000


def test_everything_the_site_uses_is_in_git():
    """A file on this disk but ignored by git would pass here and break the published site."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files", "site"], cwd=SITE.parent, capture_output=True, text=True, check=True
    ).stdout.split()
    on_disk = sorted(str(p.relative_to(SITE.parent)) for p in SITE.rglob("*") if p.is_file())
    assert [f for f in on_disk if f not in tracked] == []


def test_downloads_point_at_the_newest_release_until_the_workflow_fills_them():
    page = _page(SITE / "index.html")
    assets = {a["data-asset"]: a for a in page.all("a") if "data-asset" in a}
    assert set(assets) == {"dmg", "flatpak", "appimage"}
    for attrs in assets.values():
        assert attrs["href"] == "https://github.com/niklastshiang/stickler/releases/latest"


PAIRS = ("index.html", "about.html", "privacy.html")


def _resolved(page: Page, path: Path, names=("src", "srcset", "poster")) -> list[str]:
    found = []
    for _tag, attrs in page.tags:
        for name in names:
            for url in re.split(r",\s*", attrs.get(name, "")):
                url = url.split(" ")[0]
                if url and _local(url):
                    found.append(str(_resolve(path, url)[0].relative_to(SITE)))
    return found


@pytest.mark.parametrize("name", PAIRS)
def test_english_and_german_say_the_same(name):
    """Two hand-kept languages (SPEC "Website"): the same sections, pictures, downloads and
    outside links, and each points to the other."""
    en_path, de_path = SITE / name, SITE / "de" / name
    en, de = _page(en_path), _page(de_path)
    assert en.all("html")[0]["lang"] == "en" and de.all("html")[0]["lang"] == "de"
    assert en.ids == de.ids
    assert _resolved(en, en_path) == _resolved(de, de_path)
    for attr in ("data-asset", "data-size", "data-name", "data-copy"):
        assert [a.get(attr) for _t, a in en.tags if attr in a] == [
            a.get(attr) for _t, a in de.tags if attr in a
        ]
    outside = [a["href"] for a in en.all("a") if not _local(a.get("href", ""))]
    assert outside == [a["href"] for a in de.all("a") if not _local(a.get("href", ""))]
    alts = [(a.get("alt"), b.get("alt")) for a, b in zip(en.all("img"), de.all("img"), strict=True)]
    assert all(e != d for e, d in alts if e), "German pages have German alt texts"
    to_de = [a for a in en.all("a") if a.get("hreflang") == "de"]
    to_en = [a for a in de.all("a") if a.get("hreflang") == "en"]
    assert to_de and _resolve(en_path, to_de[0]["href"])[0] == de_path.resolve()
    assert to_en and _resolve(de_path, to_en[0]["href"])[0] == en_path.resolve()


def test_the_missing_page_speaks_both_languages_from_any_folder():
    """GitHub Pages serves one 404.html for every missing path, so it links from the root."""
    page = _page(SITE / "404.html")
    assert any(a.get("lang") == "de" for _t, a in page.tags)
    for _tag, attrs in page.tags:
        for name in ("href", "src"):
            url = attrs.get(name, "")
            if url and _local(url) and not url.startswith("#"):
                assert url.startswith("/"), url


ORIGIN = "https://stickler.tshia.ng/"
CSP = (
    "default-src 'self'; img-src 'self'; media-src 'self'; font-src 'self'; "
    "style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; form-action 'none'"
)


def _meta(page: Page) -> dict[str, str]:
    found = {}
    for attrs in page.all("meta"):
        key = attrs.get("name") or attrs.get("property") or attrs.get("http-equiv")
        if key:
            found[key.lower()] = attrs.get("content", "")
    return found


def _url(path: Path) -> str:
    rel = str(path.relative_to(SITE))
    return ORIGIN + rel.removesuffix("index.html")


@pytest.mark.parametrize("path", PAGES, ids=lambda p: str(p.relative_to(SITE)))
def test_every_page_is_safe_and_names_itself(path):
    page = _page(path)
    meta = _meta(page)
    assert meta["content-security-policy"] == CSP
    assert meta["referrer"] == "strict-origin-when-cross-origin"
    assert page.all("title")
    links = {(a.get("rel"), a.get("hreflang", "")): a.get("href", "") for a in page.all("link")}
    assert ("icon", "") in links and ("apple-touch-icon", "") in links
    if path.name == "404.html":
        assert meta["robots"] == "noindex"
        return
    assert 50 <= len(meta["description"]) <= 160, meta["description"]
    assert links[("canonical", "")] == _url(path)
    english = SITE / path.relative_to(SITE / "de") if path.parent.name == "de" else path
    german = SITE / "de" / english.relative_to(SITE)
    assert links[("alternate", "en")] == _url(english)
    assert links[("alternate", "de")] == _url(german)
    assert links[("alternate", "x-default")] == _url(english)
    assert meta["og:url"] == _url(path) and meta["og:title"] and meta["og:description"]
    assert meta["og:image"] == ORIGIN + "images/share.png"
    assert meta["og:locale"] == ("de_DE" if path.parent.name == "de" else "en_GB")


def test_the_share_picture_and_icons_have_their_sizes():
    import struct

    for name, size in (("share.png", (1200, 630)), ("icon-180.png", (180, 180))):
        head = (SITE / "images" / name).read_bytes()[:24]
        assert struct.unpack(">II", head[16:24]) == size, name


def test_search_engines_find_every_page_in_both_languages():
    robots = (SITE / "robots.txt").read_text(encoding="utf-8")
    assert "Sitemap: " + ORIGIN + "sitemap.xml" in robots
    sitemap = (SITE / "sitemap.xml").read_text(encoding="utf-8")
    pages = [p for p in PAGES if p.name != "404.html"]
    for path in pages:
        assert f"<loc>{_url(path)}</loc>" in sitemap, path
    assert sitemap.count("<url>") == len(pages)
