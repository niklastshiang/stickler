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


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.relative_to(SITE).as_posix())
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


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.relative_to(SITE).as_posix())
def test_nothing_is_loaded_from_another_server(path):
    page = _page(path)
    for tag, attrs in page.tags:
        loads = {k: v for k, v in attrs.items() if k in LOADING}
        if tag == "link" and attrs.get("rel", "") not in ("alternate", "canonical"):
            loads["href"] = attrs.get("href", "")
        for name, url in loads.items():
            for one in re.split(r",\s*", url):
                assert _local(one.split(" ")[0]), f"<{tag} {name}={url!r}>"


@pytest.mark.parametrize("path", STYLES, ids=lambda p: p.relative_to(SITE).as_posix())
def test_styles_load_nothing_from_another_server(path):
    css = path.read_text(encoding="utf-8")
    assert "@import" not in css
    for url in re.findall(r"url\(\s*['\"]?([^'\")]+)", css):
        assert _local(url), url
        assert (path.parent / url).is_file(), url


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.relative_to(SITE).as_posix())
def test_only_the_allowed_script_runs(path):
    page = _page(path)
    assert page.inline_scripts == 0
    for attrs in page.all("script"):
        assert Path(urlsplit(attrs["src"]).path).name in SCRIPTS_ALLOWED, attrs["src"]
    for _tag, attrs in page.tags:
        assert not [k for k in attrs if k.startswith("on")], attrs  # no inline handlers


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.relative_to(SITE).as_posix())
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


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.relative_to(SITE).as_posix())
def test_media_does_not_shift_the_page_and_can_be_stopped(path):
    page = _page(path)
    for attrs in page.all("img"):
        assert attrs.get("width") and attrs.get("height"), attrs  # no layout shift
    for attrs in page.all("video"):
        assert {"controls", "muted", "playsinline", "width", "height"} <= set(attrs), attrs
    for attrs in page.all("audio"):
        assert "controls" in attrs and attrs.get("preload") == "none", attrs


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.relative_to(SITE).as_posix())
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


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.relative_to(SITE).as_posix())
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
        ["git", "ls-files", "site"],
        cwd=SITE.parent,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout.split()
    on_disk = sorted(p.relative_to(SITE.parent).as_posix() for p in SITE.rglob("*") if p.is_file())
    assert [f for f in on_disk if f not in tracked] == []


def test_downloads_point_at_the_newest_release_until_the_workflow_fills_them():
    page = _page(SITE / "index.html")
    assets = {a["data-asset"]: a for a in page.all("a") if "data-asset" in a}
    assert set(assets) == {"dmg", "exe", "flatpak", "appimage", "deb", "rpm"}
    for attrs in assets.values():
        assert attrs["href"] == "https://github.com/niklastshiang/stickler/releases/latest"


PAIRS = (
    "index.html",
    "accuracy.html",
    "about.html",
    "privacy.html",
    "imprint.html",
    "install-mac.html",
    "install-windows.html",
)
# outside pages that exist in German too: the German page links the German one
LOCALISED = {
    "https://mailbox.org/en/data-protection-privacy-policy/": "https://mailbox.org/de/datenschutz/",
    "https://support.apple.com/guide/mac-help/mh40616/mac": (
        "https://support.apple.com/de-de/guide/mac-help/mh40616/mac"
    ),
    "https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation": (
        "https://learn.microsoft.com/de-de/windows/apps/package-and-deploy/smartscreen-reputation"
    ),
    "https://support.microsoft.com/en-us/windows/security/threat-malware-protection/"
    "smart-app-control-frequently-asked-questions": (
        "https://support.microsoft.com/de-de/topic/"
        "was-ist-smart-app-control-285ea03d-fa88-4d56-882e-6698afdb7003"
    ),
}


def _resolved(page: Page, path: Path, names=("src", "srcset", "poster")) -> list[str]:
    found = []
    for _tag, attrs in page.tags:
        for name in names:
            for url in re.split(r",\s*", attrs.get(name, "")):
                url = url.split(" ")[0]
                if url and _local(url):
                    found.append(_resolve(path, url)[0].relative_to(SITE).as_posix())
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
    german = [a["href"] for a in de.all("a") if not _local(a.get("href", ""))]
    assert [LOCALISED.get(url, url) for url in outside] == german
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
    rel = path.relative_to(SITE).as_posix()
    return ORIGIN + rel.removesuffix("index.html")


@pytest.mark.parametrize("path", PAGES, ids=lambda p: p.relative_to(SITE).as_posix())
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


@pytest.mark.parametrize("folder", ["", "de/"])
def test_how_it_works_is_four_steps_each_with_its_picture_hidden_from_screen_readers(folder):
    """SPEC "Website", "Change 2026-11-22": the story replaces the four cards; the text says
    everything, the pictures are decoration drawn from Stickler's output."""
    html = (SITE / folder / "index.html").read_text(encoding="utf-8")
    section = html[html.index('<section id="how"') :]
    section = section[: section.index("</section>")]
    assert section.count('<li class="story-step ') == 4 and '<ol class="story">' in section
    assert section.count('<div class="story-picture" aria-hidden="true">') == 4
    # the list numbers the steps for a screen reader; the big number is for the eye
    assert section.count('<span class="step-number" aria-hidden="true">') == 4
    assert "story-hit" in section and "story-bar" in section and "story/notes.svg" in section
    assert 'class="card"' not in section and "step-icon" not in section
    assert 'story/story.css">' in html  # each hit's and bar's part of the scroll


def _braced(css: str, start: int) -> str:
    """The text from `start` to the brace that closes the first one opened after it."""
    depth = 0
    for end in range(css.index("{", start), len(css)):
        depth += {"{": 1, "}": -1}.get(css[end], 0)
        if depth == 0:
            return css[start : end + 1]
    raise AssertionError("unbalanced braces")


def test_the_story_moves_only_where_motion_is_wanted_and_supported():
    """SPEC "Website", "Change 2026-11-22", scope 4 and 5: the motion is scroll-driven CSS, all
    of it in one block that a browser without view timelines or a visitor who asked for
    reduced motion never applies; only opacity and transform move."""
    css = (SITE / "style.css").read_text(encoding="utf-8")
    opening = (
        "@media (prefers-reduced-motion: no-preference) {\n"
        "  @supports (animation-timeline: view()) {"
    )
    assert css.count(opening) == 1
    # one column below 48rem, two from just above it: the ranges must not overlap at 48rem,
    # where the motion's sticky text would cover the picture of a one-column step (iPad, 768 px)
    one_column = css[css.index(".story-step {") :]
    one_column = one_column[: one_column.index("order: -1;")]
    assert "@media (max-width: 47.99rem) {" in one_column
    block = _braced(css, css.index(opening))
    assert "@media (min-width: 48rem)" in block
    rest = css.replace(block, "")
    assert "animation-timeline" in block and "view-timeline" in block
    assert "animation-timeline" not in rest and "view-timeline" not in rest
    assert "timeline-scope" not in css
    frames = [_braced(block, m.start()) for m in re.finditer(r"@keyframes", block)]
    assert frames
    moved = {m for f in frames for m in re.findall(r"([a-z-]+)\s*:", f)}
    assert moved <= {"opacity", "transform"}, moved


@pytest.mark.parametrize("folder", ["", "de/"])
def test_get_stickler_is_one_row_per_download_with_its_line_to_copy(folder):
    """SPEC "Website", content 9 (owner, 2026-11-22, after TuxTalk's page): one row per file,
    in this order; each Linux row has its terminal line with a copy button beside its
    download, and each download names its file for a screen reader."""
    html = (SITE / folder / "index.html").read_text(encoding="utf-8")
    section = html[html.index('<section id="get"') :]
    section = section[: section.index("</section>")]
    rows = section.split('<li class="get-row')[1:]
    assert [re.search(r'data-asset="(\w+)"', row)[1] for row in rows] == [
        "dmg",
        "exe",
        "deb",
        "rpm",
        "flatpak",
        "appimage",
    ]
    for row in rows[2:]:  # the Linux rows; the Mac's and Windows' lead to their guides
        kind = re.search(r'data-asset="(\w+)"', row)[1]
        assert f'<code id="{kind}-command">' in row and f'data-copy="{kind}-command"' in row
        assert f'<span data-name="{kind}">' in row
    for row in rows:
        assert re.search(r'<span class="visually-hidden">[^<]+: </span>', row)


@pytest.mark.parametrize("folder", ["", "de/"])
def test_the_mac_row_leads_to_the_guide(folder):
    """SPEC "Website", content 9 (owner, 2026-11-19): the Mac's download keeps one sentence and
    the link; the steps have a page of their own."""
    start = SITE / folder / "index.html"
    html = start.read_text(encoding="utf-8")
    row = html[html.index('<li class="get-row first">') :]
    row = row[: row.index("</li>")]
    assert 'data-asset="dmg"' in row
    assert 'href="install-mac.html"' in row and "<ol>" not in row
    guide = _page(SITE / folder / "install-mac.html")
    assert "xattr-command" in guide.ids, "the Terminal line for a Mac without Open Anyway"
    assert [a for _t, a in guide.tags if a.get("data-copy") == "xattr-command"]


APPLE_GUIDE = {
    "": "https://support.apple.com/guide/mac-help/mh40616/mac",
    "de/": "https://support.apple.com/de-de/guide/mac-help/mh40616/mac",
}


def test_a_placeholder_stops_the_deploy():
    """A page that still holds a placeholder (words or a picture to come) is never published:
    every placeholder there is one the workflow looks for."""
    workflow = (SITE.parent / ".github" / "workflows" / "site.yml").read_text(encoding="utf-8")
    stops = re.compile(re.search(r"grep -rnE '([^']+)' _site", workflow).group(1))
    assert stops.search("[The owner's words]") and stops.search("[Bild folgt: ein Bild]")
    for path in PAGES:
        for text in re.findall(r'class="placeholder">\s*([^<]+)', path.read_text(encoding="utf-8")):
            assert stops.search(text), (path.name, text)


@pytest.mark.parametrize("folder", ["", "de/"])
def test_the_mac_guide_leads_to_apples_own_for_the_windows_macos_shows(folder):
    """SPEC "Website", content 9 (owner, 2026-11-19): the steps in words, no pictures of our
    own; at "Open Anyway" a link to Apple's guide in the page's language."""
    path = SITE / folder / "install-mac.html"
    html = path.read_text(encoding="utf-8")
    assert 'class="placeholder"' not in html and "<picture" not in html
    steps = html[html.index('<ol class="steps">') : html.index("</ol>")]
    assert steps.count("<li>") == 5
    allow = steps[steps.index('id="step-allow"') : steps.index('id="step-confirm"')]
    assert f'href="{APPLE_GUIDE[folder]}"' in allow
    assert html.count("support.apple.com") == 1, "one link, in the page's language"


@pytest.mark.parametrize("folder", ["", "de/"])
def test_the_windows_row_leads_to_its_guide_with_microsofts_pages(folder):
    """SPEC.md, module `win-package`, scope 10: the download keeps one sentence and the link;
    the steps in words, as for the Mac, with Microsoft's own pages in the page's language."""
    html = (SITE / folder / "index.html").read_text(encoding="utf-8")
    row = html[html.index('data-asset="exe"') - 600 : html.index('data-asset="exe"')]
    assert 'href="install-windows.html"' in row
    guide = (SITE / folder / "install-windows.html").read_text(encoding="utf-8")
    assert 'class="placeholder"' not in guide and "<picture" not in guide
    assert guide[guide.index('<ol class="steps">') : guide.index("</ol>")].count("<li>") == 3
    language = "de-de" if folder else "en-us"
    assert f"learn.microsoft.com/{language}/windows/apps/package-and-deploy" in guide
    assert f"support.microsoft.com/{language}/" in guide
