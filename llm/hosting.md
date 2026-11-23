# Hosting

## Status (2026-11-22)

**Live at https://airplanemode.xin**, on GitHub Pages under its own domain (platform
decision 0019).

- DNS at Porkbun: the four GitHub Pages A records and four AAAA records on the apex,
  `www` CNAME to `jessewolcott.github.io`. The domain is verified on the GitHub account
  (TXT `_github-pages-challenge-jessewolcott`), so no other repo can claim it.
- Pages is built by **GitHub Actions** (`build_type: workflow`): the `pages` job in
  `.github/workflows/check.yml` runs on pushes to `main`, after the installer job passes,
  and publishes only `index.html`, the language folders `es/ fr/ it/ zh/ ja/ vi/`,
  `install.sh`, `assets/` and `CNAME` (the translation check job must pass too). The custom domain is
  set in the repo's Pages settings (with an Actions build the `CNAME` file is informational).
- **Enforce HTTPS** must stay on.

History:
- Decision 0011 (2026-11-21) published the repo with GitHub Pages at
  `https://jessewolcott.com/airplanemode-site/` (under the account's own Pages domain).
- Decision 0012 (same day) turned Pages **off** for that reason and planned a server of its
  own, which was never set up.
- Decision 0019 (2026-11-22) put it back on Pages with its own domain, which avoids the
  shared address.
- `.nojekyll` at the root is a leftover from the branch-built period. Harmless.

**Pushing to `main` changes what every new install runs** once CI passes (a minute or two).
The old raw URL still serves `main`'s copy too, for anyone who copied the earlier command:

```
https://raw.githubusercontent.com/jessewolcott/airplanemode-site/main/install.sh
```

Keep `main`'s `install.sh` working.

## Local preview

```sh
python -m http.server 8091    # then http://localhost:8091
```

Over http the page uses `FALLBACK_URL` (raw GitHub) for the command
(`installUrl` in `assets/site.js`). The relative "read the script" and footer `install.sh` links serve
the local file.

## Why HTTPS only

The command is `curl -fsSL <url> | sh` run as root on a router. Over plain http anyone on
the path (hotel network, captive portal) could swap the script. The page enforces this: it
only uses its own origin for the command when `location.protocol === "https:"`; otherwise it
falls back to GitHub over https. A plain-http deployment would still show a working command
(pointing at GitHub), but never at the insecure origin.

## Moving off Pages (if ever)

The site is fully static; any HTTPS static server works. Publish the same things
(`index.html`, the language folders, `install.sh` next to it, `assets/`), serve `install.sh` as plain text with
no HTML 404 pages, keep http -> https, and point the DNS there. The page needs no change.
Turn Pages off **and** remove the DNS records that point at GitHub together.
