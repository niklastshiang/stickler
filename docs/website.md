# The website

`site/` is Stickler's website (SPEC.md "Website"): plain HTML and CSS in English (`site/`) and
German (`site/de/`), for drummers who are not technical. It goes online at
**https://stickler.tshia.ng** with release 8, the release with the Mac app.

## Look at it locally

```bash
python3 -m http.server -d site 8000      # then open http://localhost:8000
```

`http.server` cannot serve byte ranges, so the video cannot be seeked there, and it shows its
own page instead of `404.html`. GitHub Pages does both.

## Change it

- **Both languages together.** Every page exists as `site/<page>.html` and
  `site/de/<page>.html`; `tests/test_site.py` fails when the two differ in sections (ids),
  pictures, downloads or outside links.
- **Facts from the repository**, not from memory: numbers from the README's results, sizes from
  the setup texts (`src/stickler_app/setup.py`), times from `docs/requirements.md`.
- **No script but `site/site.js`**, nothing from other servers, no inline styles: the Content
  Security Policy in every page allows only the site itself. The tests check it.
- **Pictures and video** come from the app, recorded with "Fluffing a Duck" (in
  `data/own/fluffing_a_duck/`, not in git), once light and once dark:

  ```bash
  scripts/gtk.sh demo "data/own/fluffing_a_duck/Fluffing a Duck.mp3" --no-gif --video site/images --stills site/images
  scripts/gtk.sh demo "data/own/fluffing_a_duck/Fluffing a Duck.mp3" --dark --no-gif --video site/images --stills site/images
  ```

  The example clip (the first 20 seconds with a click on every detected hit, as the app's
  "Both"):

  ```bash
  uv run python scripts/site_clip.py "data/own/fluffing_a_duck/Fluffing a Duck.mp3" site/media
  ```

  Close Stickler first. The recording runs the app on an invisible screen with private
  settings; only that screen's compositor gets a D-Bus session of its own.
- **Check before a commit:** `scripts/check.sh task` runs the site's tests. The accessibility
  check runs in CI; locally:

  ```bash
  curl -sSfLo /tmp/axe.tgz https://registry.npmjs.org/axe-core/-/axe-core-4.14.1.tgz
  tar -xzf /tmp/axe.tgz -C /tmp package/axe.min.js
  uvx --from playwright==1.65.2 playwright install chromium
  uvx --with playwright==1.65.2 python -I scripts/site_axe.py site /tmp/package/axe.min.js
  ```

## How it is published

`.github/workflows/site.yml` runs on every push that touches the site: the tests, then
`scripts/site_release.py` fills the download cards with the newest release's files, then
axe-core checks every page in light and dark, then the result is uploaded as a Pages artifact.
It is **published** only when

- a release from 8 on is published (the release event), or
- someone runs the workflow by hand with **deploy** ticked (Actions › site › Run workflow).

## Setting up the domain (once, by the owner)

From GitHub's documentation ("Managing a custom domain for your GitHub Pages site" and
"Verifying your custom domain for GitHub Pages", read 2026-11-18). Do the steps in this order;
verifying the domain first keeps anyone else from taking it over.

1. **Verify `tshia.ng` in the GitHub account:** GitHub › your picture › Settings › Pages › Add a
   domain › `tshia.ng`. GitHub shows a TXT record; add it at the DNS provider of `tshia.ng`
   (name `_github-pages-challenge-niklastshiang`, the value GitHub shows), wait until it
   resolves, then press Verify. A verified apex covers its subdomains.
2. **Turn Pages on for the repository:** repository › Settings › Pages › Source: **GitHub
   Actions**.
3. **The DNS record:** at the DNS provider, a `CNAME` record `stickler` → `niklastshiang.github.io`
   (without the repository's name). Check it with `dig stickler.tshia.ng +noall +answer`.
4. **The custom domain:** repository › Settings › Pages › Custom domain › `stickler.tshia.ng` ›
   Save. A workflow-published site needs no `CNAME` file.
5. **HTTPS:** once the certificate is there (up to 24 hours), tick **Enforce HTTPS**. If
   `tshia.ng` has a CAA record, it must allow `letsencrypt.org`, or no certificate is issued.
6. **Let a release deploy:** repository › Settings › Environments › `github-pages` ›
   Deployment branches and tags › add the tag rule `v*`. GitHub creates the environment for the
   default branch only, and a release runs on its tag.
7. **Publish:** Actions › site › Run workflow › deploy ✓ (or wait for release 8). A page that
   still holds a placeholder (the author's words) stops the deploy.

Until the domain works, the site is at `https://niklastshiang.github.io/stickler/` after the
first deploy; its absolute links (canonical, sitemap, Open Graph, the 404 page) point to
`stickler.tshia.ng`, and `404.html` links from the domain's root, so it looks unstyled there;
check the site at its domain.
