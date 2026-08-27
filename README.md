# JarvisPages

A tiny GitHub Pages site: a landing page (`index.html`) that links to a **Logs**
page (`logs.html`), which is generated from the run logs written by
`../run_daily.py`.

- Repo: <https://github.com/smerakm/myownjarvis>
- Live: <https://smerakm.github.io/myownjarvis/>

## How it works

- `../logs/*.log` — the source. Monthly run logs produced by `../run_daily.py`
  (a sibling directory of this repo, not tracked here).
- `scripts/build_logs.py` — parses those logs and writes `logs.html`.
- `logs.html` — generated output, committed so the site always has content.
- `.github/workflows/pages.yml` — on push to `main`, deploys `index.html` +
  `logs.html` to GitHub Pages. It does **not** regenerate `logs.html` (the log
  source lives outside the repo), so run the build locally before pushing.

## Log format (parsed, not authored)

Each `../logs/YYYY-MM.log` file is a sequence of runs:

```
===== Run at 2026-08-27 10:05:00 =====
--- Email Crawl - main ---
Status: OK
stdout:
...output...
stderr:
...output...

--- AIK Calendar - update ---
Status: FAILED (exit 1)
...
```

The script splits on `===== Run at ... =====`, then on `--- task ---`, reads the
`Status:` line into a badge (green = OK, red = failure/error, grey = skipped),
and tucks the output into a collapsible block. Long progress runs
(`fetched 40/262`, ...) are collapsed.

**Every email address in the source is replaced with `anonymous@example.com`
before rendering**, so the published page never exposes real addresses.

**Only runs from the last 30 days are rendered** (`MAX_AGE_DAYS` in the script);
older runs are ignored, even if their log file is still present.

## Build

```
python3 scripts/build_logs.py              # default: ../logs
python3 scripts/build_logs.py /path/to/logs
JARVIS_LOG_DIR=/path/to/logs python3 scripts/build_logs.py
```

Then open `index.html` in a browser, commit `logs.html`, and push.

`../run_daily.py` already does this: after writing each run to the log it calls
`publish_logs_page()`, which runs `scripts/build_logs.py` and then
`git add logs.html && git commit && git push origin main` so GitHub Pages
redeploys. The outcome is recorded in the log under `--- Publish logs page ---`
(on the *next* run, since it happens after the current run is written).

## Enabling Pages

Repo **Settings → Pages → Source = GitHub Actions**. The workflow runs on every
push to `main`; use **Actions → Deploy Pages → Run workflow** for the first
deploy or any manual redeploy.
