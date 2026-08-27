#!/usr/bin/env python3
"""Generate logs.html from the run logs produced by ../run_daily.py.

Source: a directory of monthly log files (default: ../logs/*.log, i.e. a
sibling of this repo). Each file is a sequence of runs in this shape:

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

Runs are rendered newest-first, each task with a status badge and its
output tucked into a collapsible block.

Usage:
    python3 scripts/build_logs.py [LOG_DIR]

    LOG_DIR may also be set via the JARVIS_LOG_DIR environment variable.
    CLI argument wins over the environment variable.
"""

from __future__ import annotations

import html
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_LOG_DIR = ROOT.parent / "logs"
OUT = ROOT / "logs.html"

# Runs older than this are ignored entirely.
MAX_AGE_DAYS = 30
RUN_TS_FORMAT = "%Y-%m-%d %H:%M:%S"

RUN_RE = re.compile(r"^===== Run at (.+?) =====[ \t]*$", re.MULTILINE)
TASK_RE = re.compile(r"^--- (.+?) ---\s*$")
SECTION_RE = re.compile(r"^(stdout|stderr):\s*$")
PROGRESS_RE = re.compile(
    r"^\s*(?:fetched|processed|moved to trash|deleted)\s+[\d,]+\s*/\s*[\d,]+\s*$",
    re.IGNORECASE,
)
NOISE_RE = re.compile(r"^Shell cwd was reset to ")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
ANON_EMAIL = "anonymous@example.com"


def scrub(text: str) -> str:
    """Replace every email address with an anonymous placeholder."""
    return EMAIL_RE.sub(ANON_EMAIL, text)

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Logs &middot; Jarvis</title>
  <style>
    :root {{
      --bg: #0d1117; --panel: #161b22; --border: #30363d;
      --text: #e6edf3; --muted: #8b949e; --accent: #58a6ff;
      --ok: #3fb950; --bad: #f85149; --skip: #8b949e;
    }}
    @media (prefers-color-scheme: light) {{
      :root {{
        --bg: #ffffff; --panel: #f6f8fa; --border: #d0d7de;
        --text: #1f2328; --muted: #59636e; --accent: #0969da;
        --ok: #1a7f37; --bad: #cf222e; --skip: #59636e;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; padding: 2rem 1.5rem;
      background: var(--bg); color: var(--text);
      font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    }}
    main {{ max-width: 780px; margin: 0 auto; }}
    a {{ color: var(--accent); }}
    .back {{ text-decoration: none; font-size: .9rem; }}
    h1 {{ margin: .75rem 0 .25rem; letter-spacing: -0.02em; }}
    .built {{ color: var(--muted); font-size: .85rem; margin-bottom: 2.5rem; }}
    .run {{
      border: 1px solid var(--border); border-radius: 12px;
      background: var(--panel); padding: 1.25rem 1.5rem; margin-bottom: 1.25rem;
    }}
    .run > h2 {{
      margin: 0 0 1rem; font-size: 1.05rem;
      font-variant-numeric: tabular-nums;
    }}
    .task {{ margin: .75rem 0; }}
    .task-head {{
      display: flex; align-items: center; gap: .6rem; flex-wrap: wrap;
      font-weight: 600;
    }}
    .badge {{
      font-size: .72rem; font-weight: 700; letter-spacing: .03em;
      text-transform: uppercase; padding: .1rem .45rem; border-radius: 999px;
      border: 1px solid currentColor;
    }}
    .badge.ok {{ color: var(--ok); }}
    .badge.bad {{ color: var(--bad); }}
    .badge.skip {{ color: var(--skip); }}
    details {{ margin: .4rem 0 0; }}
    summary {{ cursor: pointer; color: var(--muted); font-size: .85rem; }}
    pre {{
      margin: .5rem 0 0; padding: .75rem 1rem; overflow-x: auto;
      background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
      font: 13px/1.5 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }}
    .empty {{ color: var(--muted); }}
  </style>
</head>
<body>
  <main>
    <a class="back" href="index.html">&larr; Jarvis</a>
    <h1>Logs</h1>
    <p class="built">Rebuilt {built} &middot; source: {source} &middot; last {days} days</p>
{body}
  </main>
</body>
</html>
"""


def compact(lines: list[str]) -> list[str]:
    """Collapse long runs of progress lines (`fetched 40/262`, ...)."""
    out: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        if PROGRESS_RE.match(lines[i]):
            j = i
            while j < n and PROGRESS_RE.match(lines[j]):
                j += 1
            block = lines[i:j]
            if len(block) > 3:
                out.append(block[0])
                out.append(f"    ... {len(block) - 2} more progress lines ...")
                out.append(block[-1])
            else:
                out.extend(block)
            i = j
        else:
            out.append(lines[i])
            i += 1
    return out


def status_class(status: str) -> str:
    s = status.upper()
    if s.startswith("OK"):
        return "ok"
    if "SKIP" in s:
        return "skip"
    return "bad"


def parse_run_body(body: str) -> list[dict]:
    """Split a single run's text into task dicts."""
    tasks: list[dict] = []
    current: dict | None = None
    section: str | None = None

    for raw in body.splitlines():
        if NOISE_RE.match(raw):
            continue
        m = TASK_RE.match(raw)
        if m:
            current = {"name": m.group(1), "status": "", "output": []}
            tasks.append(current)
            section = None
            continue
        if current is None:
            continue
        if not current["status"]:
            if raw.startswith("Status:"):
                current["status"] = raw[len("Status:"):].strip()
                continue
            if raw.strip().startswith("SKIPPED"):
                current["status"] = raw.strip()
                continue
        if SECTION_RE.match(raw):
            section = SECTION_RE.match(raw).group(1)
            current["output"].append(f"[{section}]")
            continue
        current["output"].append(raw)

    for t in tasks:
        while t["output"] and not t["output"][0].strip():
            t["output"].pop(0)
        while t["output"] and not t["output"][-1].strip():
            t["output"].pop()
        if not t["status"]:
            t["status"] = "UNKNOWN"
    return tasks


def parse_logs(log_dir: Path) -> list[dict]:
    """Return runs from the last MAX_AGE_DAYS days, newest first."""
    cutoff = datetime.now() - timedelta(days=MAX_AGE_DAYS)
    runs: list[dict] = []
    dropped = 0

    for path in sorted(log_dir.glob("*.log")):
        text = scrub(path.read_text(encoding="utf-8", errors="replace"))
        chunks = RUN_RE.split(text)
        # chunks: [pre, ts1, body1, ts2, body2, ...]
        for k in range(1, len(chunks), 2):
            ts = chunks[k].strip()
            body = chunks[k + 1] if k + 1 < len(chunks) else ""
            try:
                when = datetime.strptime(ts, RUN_TS_FORMAT)
            except ValueError:
                when = None
            if when is not None and when < cutoff:
                dropped += 1
                continue
            runs.append(
                {
                    "timestamp": ts,
                    "when": when,
                    "file": path.name,
                    "tasks": parse_run_body(body),
                }
            )

    if dropped:
        print(f"ignored {dropped} run(s) older than {MAX_AGE_DAYS} days")

    runs.sort(key=lambda r: r["when"] or datetime.min, reverse=True)
    return runs


def render(runs: list[dict]) -> str:
    if not runs:
        return (
            '    <section class="run"><p class="empty">'
            f"No runs in the last {MAX_AGE_DAYS} days.</p></section>"
        )

    blocks: list[str] = []
    for run in runs:
        rows: list[str] = []
        for task in run["tasks"]:
            cls = status_class(task["status"])
            name = html.escape(task["name"])
            status = html.escape(task["status"])
            row = [
                '    <div class="task">',
                '      <div class="task-head">',
                f"        <span>{name}</span>",
                f'        <span class="badge {cls}">{status}</span>',
                "      </div>",
            ]
            output = compact(task["output"])
            if output:
                pre = html.escape("\n".join(output))
                row += [
                    "      <details>",
                    "        <summary>output</summary>",
                    f"        <pre>{pre}</pre>",
                    "      </details>",
                ]
            row.append("    </div>")
            rows.append("\n".join(row))

        heading = html.escape(run["timestamp"] or "unknown time")
        body = "\n".join(rows) if rows else '    <p class="empty">No tasks recorded.</p>'
        blocks.append(
            f'  <section class="run">\n    <h2>{heading}</h2>\n{body}\n  </section>'
        )
    return "\n".join(blocks)


def main() -> int:
    log_dir = Path(
        sys.argv[1] if len(sys.argv) > 1 else os.environ.get("JARVIS_LOG_DIR", DEFAULT_LOG_DIR)
    ).expanduser()

    if not log_dir.is_dir():
        print(f"warning: log dir {log_dir} not found; writing empty logs page", file=sys.stderr)
        runs: list[dict] = []
        source = f"{log_dir} (missing)"
    else:
        runs = parse_logs(log_dir)
        try:
            source = log_dir.relative_to(ROOT.parent).as_posix()
        except ValueError:
            source = str(log_dir)

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    OUT.write_text(
        PAGE.format(
            built=built, source=html.escape(source), days=MAX_AGE_DAYS, body=render(runs)
        ),
        encoding="utf-8",
    )
    task_count = sum(len(r["tasks"]) for r in runs)
    print(f"wrote {OUT} ({len(runs)} run(s), {task_count} task(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
