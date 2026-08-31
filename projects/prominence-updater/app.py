#!/usr/bin/env python3
"""Prominence updater dashboard — upload, protect files, stage, and live-apply."""
from __future__ import annotations

import html
import hmac
import json
import os
import re
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from updater_core import (
    ConfirmationRequired,
    CraftyControl,
    UnsafeArchiveError,
    VelocityMaintenanceToggle,
    derive_candidate_version,
    inspect_zip,
    list_protected_entries,
    list_server_files,
    live_apply_archive,
    protect_path,
    require_force_confirmation,
    stage_archive,
    unprotect_path,
)

ROOT = Path(os.environ.get(
    "PROMINENCE_ROOT",
    "/data/compose/13/docker/servers/50a6d163-0309-4832-986f-106668768b3d",
))
CONFIG = Path(os.environ.get("PROMINENCE_UPDATER_CONFIG", "/etc/prominence-updater.json"))
STAGING = Path(os.environ.get("PROMINENCE_UPDATER_STAGING", "staging"))
BACKUP_ROOT = Path(os.environ.get("PROMINENCE_UPDATER_BACKUPS", "backups"))

CRAFTY_BASE = os.environ.get("CRAFTY_BASE", "https://<INTERNAL_IP_REDACTED>.11:8443")
CRAFTY_SERVER_ID = os.environ.get("CRAFTY_SERVER_ID", "50a6d163-0309-4832-986f-106668768b3d")
CRAFTY_TOKEN_FILE = Path(os.environ.get("CRAFTY_TOKEN_FILE", "/etc/prominence-daily-restart.token"))

VELOCITY_MAINTENANCE_CONFIG = Path(os.environ.get(
    "VELOCITY_MAINTENANCE_CONFIG",
    "/data/compose/13/docker/servers/43ac65de-795f-443f-9cc5-2aecc7447a05/plugins/maintenance/config.yml",
))
MINIMOTD_MAIN_CONF = Path(os.environ.get(
    "MINIMOTD_MAIN_CONF",
    "/data/compose/13/docker/servers/43ac65de-795f-443f-9cc5-2aecc7447a05/plugins/minimotd-velocity/main.conf",
))
OVERLAY_DIR_NAME = os.environ.get("OVERLAY_DIR_NAME", "Dontdeleteimportantmods")

# Modrinth public API — no key required, always returns latest version
MODRINTH_API = "https://api.modrinth.com/v2/project/EGs3lC8D/version?loaders=[%22fabric%22]&game_versions=[%221.20.1%22]&limit=5"

MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024

DEFAULT: dict = {
    "auto_update": False,
    "protected_paths": [
        "importantmods/", "fabric.jar", "server.properties",
        "variables.txt", "world/", "worldnopregen/",
    ],
    "protected_entries": [],
    "protect_job": None,        # {path, copied, total, status: running|done|error, error_msg}
    "last_check": None,
    "last_result": "No archive uploaded.",
    "server_pack_url": "",
    "installed_version": "unknown",
    "installed_version_override": None,   # manual override; when set, wins over jar auto-detect
    "candidate_version": None,
    "candidate_archive": None,
}

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(config: Path) -> dict:
    try:
        return DEFAULT | json.loads(config.read_text())
    except FileNotFoundError:
        return DEFAULT.copy()


def save_config(config: Path, data: dict) -> None:
    config.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, config)


def installed_version(root: Path) -> str:
    mods = root / "mods"
    matches = list(mods.glob("Prominent-GLOBAL-MC1.20.1-*.jar")) if mods.is_dir() else []
    match = re.search(r"-(\d+\.\d+\.\d+(?:hf)?)\.jar$", matches[0].name) if matches else None
    return match.group(1) if match else "unknown"


VERSION_RE = re.compile(r"\d+\.\d+\.\d+(?:hf)?")


def effective_installed_version(state: dict, root: Path) -> str:
    """Return the manual override if one is set, else the jar-detected version."""
    override = state.get("installed_version_override")
    if override:
        return override
    return installed_version(root)


def latest_curseforge_version() -> str:
    """Fetch the latest Hasturian Era version from Modrinth (open API, no key needed)."""
    headers = {"User-Agent": "ProminenceUpdater/2.0 (contact: admin@server)"}
    try:
        req = urllib.request.Request(MODRINTH_API, headers=headers)
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            versions = json.loads(resp.read())
            for v in versions:
                num = v.get("version_number", "")
                if re.fullmatch(r"\d+\.\d+\.\d+(?:hf)?", num):
                    return num
    except Exception as e:
        return f"unavailable ({e})"
    return "unavailable"


def _read_crafty_token() -> str | None:
    try:
        token = CRAFTY_TOKEN_FILE.read_text(encoding="utf-8").strip()
        return token if token else None
    except OSError:
        return None


def _live_status(root: Path) -> dict:
    result = {"player_count": "?", "maintenance": "?", "crafty_ok": False}
    token = _read_crafty_token()
    if token:
        try:
            crafty = CraftyControl(CRAFTY_BASE, CRAFTY_SERVER_ID, token)
            result["player_count"] = crafty.player_count()
            result["crafty_ok"] = True
        except Exception as e:
            result["player_count"] = f"err"
    try:
        maint = VelocityMaintenanceToggle(VELOCITY_MAINTENANCE_CONFIG)
        result["maintenance"] = "ON" if maint.is_enabled() else "off"
    except Exception:
        pass
    return result


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font: 15px/1.6 'Inter', system-ui, sans-serif;
  background: #0d1117;
  color: #c9d1d9;
  min-height: 100vh;
}
a { color: #58a6ff; text-decoration: none; }
a:hover { text-decoration: underline; }

/* Layout */
.page { max-width: 1060px; margin: 0 auto; padding: 1.5rem 1rem 4rem; }
header {
  display: flex; align-items: center; gap: 1rem;
  padding: 1rem 0 1.5rem;
  border-bottom: 1px solid #21262d;
  margin-bottom: 1.5rem;
}
header h1 { font-size: 1.3rem; font-weight: 700; color: #f0f6fc; }
header .badge {
  font-size: .75rem; padding: .2rem .6rem;
  border-radius: 20px; font-weight: 600;
  background: #21262d; color: #8b949e;
}

/* Stats bar */
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: .75rem;
  margin-bottom: 1.5rem;
}
.stat-card {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 10px;
  padding: .9rem 1.1rem;
}
.stat-card .label { font-size: .72rem; text-transform: uppercase; letter-spacing: .06em; color: #8b949e; margin-bottom: .35rem; }
.stat-card .value { font-size: 1.35rem; font-weight: 700; color: #f0f6fc; }
.stat-card .value.green { color: #3fb950; }
.stat-card .value.red   { color: #f85149; }
.stat-card .value.yellow{ color: #d29922; }

/* Cards */
.card {
  background: #161b22;
  border: 1px solid #21262d;
  border-radius: 12px;
  padding: 1.25rem 1.4rem;
  margin-bottom: 1rem;
}
.card.danger { border-color: #6e2929; background: #160d0d; }
.card h2 {
  font-size: 1rem; font-weight: 700; color: #f0f6fc;
  margin-bottom: .9rem;
  display: flex; align-items: center; gap: .5rem;
}
.card h2 .icon { font-size: 1.1rem; }

/* Alerts */
.alert {
  border-radius: 8px; padding: .75rem 1rem;
  margin-bottom: 1rem; font-size: .88rem;
}
.alert-warn { background: #272115; border: 1px solid #6e4c1e; color: #d29922; }
.alert-info { background: #0f1f2e; border: 1px solid #1f4068; color: #58a6ff; }
.alert-ok   { background: #0f1f0f; border: 1px solid #1a4d1a; color: #3fb950; }
.alert-err  { background: #200d0d; border: 1px solid #6e1818; color: #f85149; }

/* Forms */
label { display: block; font-size: .85rem; color: #8b949e; margin-bottom: .3rem; }
input[type=text], input[type=file] {
  width: 100%; padding: .55rem .75rem;
  background: #0d1117; border: 1px solid #30363d;
  border-radius: 8px; color: #c9d1d9; font: inherit;
}
input[type=text]:focus { outline: 2px solid #58a6ff; border-color: #58a6ff; }

/* Buttons */
.btn {
  display: inline-flex; align-items: center; gap: .45rem;
  padding: .55rem 1.1rem; border: 1px solid transparent;
  border-radius: 8px; font: inherit; font-weight: 600; font-size: .88rem;
  cursor: pointer; text-decoration: none; transition: opacity .15s;
}
.btn:disabled { opacity: .4; cursor: not-allowed; }
.btn-primary  { background: #238636; border-color: #2ea043; color: #fff; }
.btn-blue     { background: #1f6feb; border-color: #388bfd; color: #fff; }
.btn-danger   { background: #b62324; border-color: #c93535; color: #fff; }
.btn-ghost    { background: transparent; border-color: #30363d; color: #c9d1d9; }
.btn-sm       { padding: .3rem .7rem; font-size: .8rem; }
.btn:hover:not(:disabled) { opacity: .85; }

/* File browser */
.filebrowser { font-size: .85rem; }
.fb-row {
  display: flex; align-items: center; gap: .6rem;
  padding: .45rem .6rem;
  border-radius: 6px;
  border: 1px solid transparent;
  transition: background .1s;
}
.fb-row:hover { background: #21262d; }
.fb-row.protected { background: #0f1f0f; border-color: #1a3d1a; }
.fb-icon { width: 1.2rem; text-align: center; flex-shrink: 0; }
.fb-name { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: #c9d1d9; }
.fb-size { color: #8b949e; font-size: .78rem; min-width: 4rem; text-align: right; }
.fb-badge { font-size: .7rem; padding: .15rem .45rem; border-radius: 4px;
             background: #1a3d1a; color: #3fb950; font-weight: 700; }
.fb-actions { display: flex; gap: .4rem; flex-shrink: 0; }
.fb-breadcrumb { font-size: .82rem; color: #8b949e; margin-bottom: .75rem; }
.fb-breadcrumb a { color: #58a6ff; }
.fb-empty { padding: 1rem; text-align: center; color: #484f58; font-style: italic; }

/* Protected list */
.prot-list { list-style: none; }
.prot-list li {
  display: flex; align-items: center; gap: .5rem;
  padding: .4rem .5rem; border-radius: 6px;
  font-size: .84rem;
}
.prot-list li:hover { background: #21262d; }
.prot-list li .ppath { flex: 1; font-family: monospace; color: #79c0ff; }
.prot-list li .psize { color: #8b949e; font-size: .78rem; }

.confirm-row { display: flex; gap: .6rem; align-items: flex-end; margin-top: .8rem; }
.confirm-row input { flex: 1; }
.hint { font-size: .78rem; color: #6e7681; margin-top: .35rem; }
code { font-family: monospace; color: #79c0ff; background: #0d1117; padding: .1em .35em; border-radius: 4px; }
hr { border: 0; border-top: 1px solid #21262d; margin: 1rem 0; }
.cols2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
@media(max-width:680px){ .cols2 { grid-template-columns: 1fr; } }
"""

def _fmt_size(n: int | None) -> str:
    if n is None:
        return ""
    for unit in ("B","KB","MB","GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def _render_filebrowser(root: Path, overlay_dir_name: str, rel_path: str | None = None,
                        protected_entries: list[str] | None = None) -> str:
    try:
        items = list_server_files(root, rel_path, overlay_dir_name)
    except Exception as e:
        return f'<div class="alert alert-err">Cannot read directory: {html.escape(str(e))}</div>'

    # Breadcrumb
    parts = [f'<a href="/files">server root</a>']
    if rel_path:
        acc = ""
        for seg in rel_path.split("/"):
            acc = f"{acc}/{seg}".lstrip("/")
            parts.append(f'<a href="/files?p={urllib.parse.quote(acc)}">{html.escape(seg)}</a>')
    breadcrumb = f'<div class="fb-breadcrumb">📁 {" / ".join(parts)}</div>'

    if not items:
        return breadcrumb + '<div class="fb-empty">Empty directory</div>'

    rows = []
    entries_set = set(e.rstrip("/") for e in (protected_entries or []))
    for it in items:
        rel = it["path"]
        # Item is protected if: itself is an entry, OR any ancestor dir is an entry
        check = Path(rel)
        item_protected = False
        while str(check) != ".":
            if str(check) in entries_set:
                item_protected = True
                break
            check = check.parent
        it = dict(it, protected=item_protected)
        esc_name = html.escape(it["name"])
        esc_path = html.escape(it["path"])
        icon = "📁" if it["type"] == "dir" else "📄"
        size_str = _fmt_size(it.get("size"))
        prot_class = " protected" if it["protected"] else ""
        badge = '<span class="fb-badge">✓ PROTECTED</span>' if it["protected"] else ""

        if it["type"] == "dir":
            name_html = f'<a class="fb-name" href="/files?p={urllib.parse.quote(it["path"])}">{esc_name}/</a>'
        else:
            name_html = f'<span class="fb-name">{esc_name}</span>'

        if it["protected"]:
            action = (f'<form method="post" action="/unprotect" style="display:inline">'
                      f'<input type="hidden" name="path" value="{esc_path}">'
                      f'<button class="btn btn-ghost btn-sm" type="submit">Remove</button></form>')
        else:
            action = (f'<form method="post" action="/protect" style="display:inline">'
                      f'<input type="hidden" name="path" value="{esc_path}">'
                      f'<button class="btn btn-primary btn-sm" type="submit">🔒 Protect</button></form>')

        rows.append(
            f'<div class="fb-row{prot_class}">'
            f'  <span class="fb-icon">{icon}</span>'
            f'  {name_html}'
            f'  {badge}'
            f'  <span class="fb-size">{size_str}</span>'
            f'  <div class="fb-actions">{action}</div>'
            f'</div>'
        )

    return breadcrumb + '<div class="filebrowser">' + "\n".join(rows) + "</div>"


def _render_protected_list(overlay_dir: Path, entries: list[str]) -> str:
    items = list_protected_entries(overlay_dir, entries)
    if not items:
        return '<p class="hint">No files protected yet. Browse the server files below and click <b>🔒 Protect</b> on any file or folder.</p>'
    rows = []
    for it in items:
        esc = html.escape(it["path"])
        quoted = urllib.parse.quote(it["path"].rstrip("/"), safe="")
        if it["type"] == "dir":
            icon = "📁"
            meta = f'<span class="psize">{it["count"]} file{"s" if it["count"] != 1 else ""}</span>'
        else:
            icon = "📄"
            meta = f'<span class="psize">{_fmt_size(it["size"])}</span>'
        rows.append(
            f'<li>'
            f'<span style="font-size:1rem">{icon}</span>'
            f'<span class="ppath">{esc}</span>'
            f'{meta}'
            f'<form method="post" action="/unprotect" style="display:inline">'
            f'<input type="hidden" name="path" value="{quoted}">'
            f'<button class="btn btn-ghost btn-sm" type="submit">✕</button>'
            f'</form>'
            f'</li>'
        )
    return '<ul class="prot-list">' + "\n".join(rows) + "</ul>"


def dashboard(state: dict, live: dict, root: Path, overlay_dir: Path,
              file_path: str | None = None, overlay_dir_name: str = OVERLAY_DIR_NAME) -> str:
    inst = html.escape(state.get("installed_version", "unknown"))
    inst_override = bool(state.get("installed_version_override"))
    cand = html.escape(state.get("candidate_version") or "none")
    cand_raw = state.get("candidate_version") or ""
    status = html.escape(state.get("last_result", ""))
    players = live.get("player_count", "?")
    maint = live.get("maintenance", "?")
    maint_color = "red" if maint == "ON" else "green"
    players_color = "red" if isinstance(players, int) and players > 0 else "green"

    apply_ok = isinstance(players, int) and players == 0 and cand_raw
    apply_disabled = "" if apply_ok else "disabled"

    result_alert = ""
    if status:
        cls = "alert-ok" if "applied" in status.lower() or "saved" in status.lower() or "stored" in status.lower() or "protected" in status.lower() or "removed" in status.lower() else "alert-warn"
        if "error" in status.lower() or "fail" in status.lower() or "err:" in status.lower():
            cls = "alert-err"
        result_alert = f'<div class="alert {cls}">{status}</div>'

    # Protect job progress banner
    job = state.get("protect_job")
    job_banner = ""
    if job and job.get("status") == "running":
        copied = job.get("copied", 0)
        total = job.get("total", 1) or 1
        pct = int(copied / total * 100)
        job_banner = f"""
<div class="alert alert-info" style="padding:1rem" id="protect-progress">
  <div style="display:flex;justify-content:space-between;margin-bottom:.5rem">
    <span>🔒 Protecting <code>{html.escape(job.get('path',''))}</code>…</span>
    <span>{copied:,} / {total:,} files ({pct}%)</span>
  </div>
  <div style="background:#21262d;border-radius:6px;height:8px;overflow:hidden">
    <div style="background:#1f6feb;width:{pct}%;height:100%;transition:width .3s"></div>
  </div>
</div>
<script>setTimeout(()=>location.reload(),2000)</script>"""
    elif job and job.get("status") == "error":
        job_banner = f'<div class="alert alert-err">Protection failed for <code>{html.escape(job.get("path",""))}</code>: {html.escape(job.get("error_msg",""))}</div>'

    filebrowser_html = _render_filebrowser(root, overlay_dir_name, file_path,
                                           state.get("protected_entries", []))
    protected_html = _render_protected_list(overlay_dir, state.get("protected_entries", []))

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Prominence Updater</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<style>{CSS}</style>
</head><body>
<div class="page">

<header>
  <div>
    <h1>⚡ Prominence II Updater</h1>
    <div style="color:#8b949e;font-size:.82rem;margin-top:.2rem">Hasturian Era — server management console</div>
  </div>
</header>

{result_alert}

{job_banner}

<!-- Stats bar -->
<div class="stats">
  <div class="stat-card">
    <div class="label">Installed{' (manual)' if inst_override else ''}</div>
    <div class="value{' yellow' if inst_override else ''}">v{inst}</div>
  </div>
  <div class="stat-card">
    <div class="label">Candidate</div>
    <div class="value {'yellow' if cand_raw else ''}">v{cand}</div>
  </div>
  <div class="stat-card">
    <div class="label">Players Online</div>
    <div class="value {players_color}">{players}</div>
  </div>
  <div class="stat-card">
    <div class="label">Maintenance</div>
    <div class="value {maint_color}">{maint}</div>
  </div>
</div>

<!-- Upload -->
<div class="card">
  <h2><span class="icon">📦</span> Upload Server Pack ZIP</h2>
  <p style="font-size:.85rem;color:#8b949e;margin-bottom:.9rem">
    Download the new pack ZIP from CurseForge, then upload here.
    The file is inspected for unsafe paths before storage — nothing touches the live server.
  </p>
  <form action="/upload" method="post" enctype="multipart/form-data">
    <label>Select ZIP file</label>
    <input type="file" name="archive" accept=".zip,application/zip" required>
    <div style="margin-top:.75rem">
      <button class="btn btn-blue" type="submit">📤 Inspect &amp; Store Candidate</button>
    </div>
  </form>
  <form method="post" action="/check" style="margin-top:.75rem">
    <button class="btn btn-ghost" type="submit">🔍 Check Latest Version</button>
  </form>
</div>

<!-- Manual version override -->
<div class="card">
  <h2><span class="icon">✏️</span> Set Current Version</h2>
  <p style="font-size:.83rem;color:#8b949e;margin-bottom:.9rem">
    Manually override the detected installed version when the jar filename is wrong or lags reality.
    This only changes what the dashboard reports; it doesn't touch any files. Leave blank and save to
    clear the override and revert to auto-detection from the mods jar.
  </p>
  <form method="post" action="/set-version">
    <label>Installed version</label>
    <input type="text" name="version" value="{html.escape(state.get('installed_version_override') or '')}"
           placeholder="{inst}" autocomplete="off">
    <p class="hint">Format like <code>4.0.3</code> or <code>4.0.3hf</code>. {'<b>Currently overridden.</b> ' if inst_override else ''}Blank + Save reverts to auto-detect.</p>
    <div style="margin-top:.75rem">
      <button class="btn btn-blue" type="submit">💾 Save Version</button>
    </div>
  </form>
</div>

<!-- Apply -->
<div class="cols2">
  <div class="card">
    <h2><span class="icon">▶</span> Apply Update</h2>
    <p style="font-size:.83rem;color:#8b949e;margin-bottom:.9rem">
      Full sequence: maintenance on → backup → apply files → restore protected mods → update MOTD → restart → health check → maintenance off.
      <b>Requires zero players.</b>
    </p>
    <form action="/apply" method="post">
      <label>Confirmation</label>
      <input type="text" name="confirm" placeholder="APPLY {cand_raw}" autocomplete="off">
      <p class="hint">Type exactly: <code>APPLY {cand_raw}</code></p>
      <div style="margin-top:.75rem">
        <button class="btn btn-primary" type="submit" {apply_disabled}
          title="{'Players online — wait or use Force' if not apply_ok else 'Apply update'}">
          ▶ Apply Update
        </button>
      </div>
    </form>
  </div>

  <div class="card danger">
    <h2><span class="icon">⚡</span> Force Update</h2>
    <p style="font-size:.83rem;color:#8b949e;margin-bottom:.9rem">
      Bypasses the zero-player gate only. Archive inspection, backups, protected paths,
      maintenance mode, and health checks are all still enforced.
    </p>
    <form action="/force" method="post">
      <label>Confirmation</label>
      <input type="text" name="confirm" placeholder="FORCE UPDATE {cand_raw}" autocomplete="off">
      <p class="hint">Type exactly: <code>FORCE UPDATE {cand_raw}</code></p>
      <div style="margin-top:.75rem">
        <button class="btn btn-danger" type="submit">⚡ Force Update</button>
      </div>
    </form>
  </div>
</div>

<!-- Protected files -->
<div class="card">
  <h2><span class="icon">🔒</span> Protected Files</h2>
  <p style="font-size:.83rem;color:#8b949e;margin-bottom:.9rem">
    Protected files are copied into <code>Dontdeleteimportantmods/</code> and automatically
    restored on top of the pack after every update, even if the pack deletes them.
    Browse the server files below and click <b>Protect</b> on any file or folder.
  </p>
  {protected_html}
</div>

<!-- File browser -->
<div class="card">
  <h2><span class="icon">📁</span> Server Files</h2>
  <p style="font-size:.83rem;color:#8b949e;margin-bottom:.75rem">
    Click any file or folder to browse. Click <b>🔒 Protect</b> to preserve it across updates.
  </p>
  {filebrowser_html}
</div>

<!-- Stage (advanced) -->
<details style="margin-bottom:1rem">
  <summary style="cursor:pointer;color:#8b949e;font-size:.85rem;padding:.5rem 0">
    ▸ Advanced: Non-live staging
  </summary>
  <div class="card" style="margin-top:.5rem">
    <h2><span class="icon">🔬</span> Stage Candidate (non-live)</h2>
    <p style="font-size:.83rem;color:#8b949e;margin-bottom:.9rem">
      Extracts the pack into a staging directory for inspection. The live server is not changed.
    </p>
    <form action="/stage" method="post">
      <label>Confirmation</label>
      <input type="text" name="confirm" placeholder="STAGE {cand_raw}" autocomplete="off">
      <p class="hint">Type exactly: <code>STAGE {cand_raw}</code></p>
      <div style="margin-top:.75rem">
        <button class="btn btn-ghost" type="submit">🔬 Build Stage</button>
      </div>
    </form>
  </div>
</details>

</div><!-- .page -->
</body></html>"""


# ---------------------------------------------------------------------------
# HTTP parsing helpers
# ---------------------------------------------------------------------------

def _form_data(handler: BaseHTTPRequestHandler) -> dict[str, str]:
    length = int(handler.headers.get("Content-Length", "0"))
    raw = handler.rfile.read(length).decode("utf-8", "replace")
    # parse_qs decodes %XX sequences correctly; + is treated as space in form data
    # but we percent-encode path values in the HTML so + arrives as %2B → preserved
    return {k: v[-1] for k, v in urllib.parse.parse_qs(raw, keep_blank_values=True).items()}


def _multipart_upload(handler: BaseHTTPRequestHandler) -> tuple[str, bytes]:
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0 or length > MAX_UPLOAD_BYTES:
        raise UnsafeArchiveError("upload size is outside policy")
    content_type = handler.headers.get("Content-Type", "")
    if "multipart/form-data" not in content_type:
        raise UnsafeArchiveError("archive must use multipart/form-data")
    raw = handler.rfile.read(length)
    message = BytesParser(policy=default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + raw
    )
    for part in message.iter_parts():
        if part.get_param("name", header="content-disposition") == "archive":
            filename = part.get_filename() or ""
            if not filename or Path(filename).name != filename or not filename.lower().endswith(".zip"):
                raise UnsafeArchiveError("archive filename must be a plain .zip filename")
            return filename, part.get_payload(decode=True) or b""
    raise UnsafeArchiveError("missing archive upload field")


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------

def make_handler(
    root: Path = ROOT,
    config: Path = CONFIG,
    staging: Path = STAGING,
    backup_root: Path = BACKUP_ROOT,
    auth_token: str | None = None,
    crafty_base: str = CRAFTY_BASE,
    crafty_server_id: str = CRAFTY_SERVER_ID,
    crafty_token_file: Path = CRAFTY_TOKEN_FILE,
    velocity_maintenance_config: Path = VELOCITY_MAINTENANCE_CONFIG,
    minimotd_conf: Path = MINIMOTD_MAIN_CONF,
    overlay_dir_name: str = OVERLAY_DIR_NAME,
):
    overlay_dir = root / overlay_dir_name

    class Handler(BaseHTTPRequestHandler):
        def _authorized(self) -> bool:
            if auth_token is None:
                return True
            return hmac.compare_digest(
                self.headers.get("Authorization", ""),
                f"Bearer {auth_token}",
            )

        def _require_authorized(self) -> bool:
            if self._authorized():
                return True
            self._send(401, b"authentication required", "text/plain")
            return False

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, value: dict) -> None:
            self._send(status, json.dumps(value).encode(), "application/json")

        def _redirect(self, location: str = "/") -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def _get_crafty(self) -> CraftyControl:
            try:
                token = crafty_token_file.read_text(encoding="utf-8").strip()
                if not token:
                    raise RuntimeError("Crafty token file is empty")
            except OSError as e:
                raise RuntimeError(f"Cannot read Crafty token: {e}") from e
            return CraftyControl(crafty_base, crafty_server_id, token)

        def _render_dashboard(self, state: dict, file_path: str | None = None) -> bytes:
            state["installed_version"] = effective_installed_version(state, root)
            live = _live_status(root)
            return dashboard(
                state, live, root, overlay_dir, file_path, overlay_dir_name
            ).encode()

        # --- GET ---
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            file_path = qs.get("p", [None])[0]

            state = load_config(config)
            save_config(config, state)
            self._send(200, self._render_dashboard(state, file_path), "text/html; charset=utf-8")

        # --- POST ---
        def do_POST(self):
            if not self._require_authorized():
                return
            state = load_config(config)
            state["installed_version"] = effective_installed_version(state, root)
            try:
                parsed_path = urllib.parse.urlparse(self.path).path

                # ---- Upload ----
                if parsed_path == "/upload":
                    filename, data = _multipart_upload(self)
                    report = inspect_zip(data, state["protected_paths"])
                    if report.rejected:
                        raise UnsafeArchiveError("rejected archive paths: " + ", ".join(report.rejected))
                    uploads = staging / "uploads"
                    uploads.mkdir(parents=True, exist_ok=True)
                    target = uploads / filename
                    if target.exists():
                        raise UnsafeArchiveError("candidate already exists; choose a unique filename")
                    target.write_bytes(data)
                    candidate = derive_candidate_version(filename, None)
                    state.update(
                        candidate_version=candidate,
                        candidate_archive=filename,
                        last_result=f"✓ Candidate v{candidate} inspected and stored. Ready to apply.",
                    )
                    save_config(config, state)
                    self._redirect()
                    return

                # ---- Stage ----
                if parsed_path == "/stage":
                    form = _form_data(self)
                    candidate = state.get("candidate_version")
                    if not candidate or form.get("confirm") != f"STAGE {candidate}":
                        raise UnsafeArchiveError(f"type exactly: STAGE {candidate or '<candidate>'}")
                    archive = staging / "uploads" / str(state["candidate_archive"])
                    result = stage_archive(archive, root, staging, state["protected_paths"], overlay_dir_name)
                    state["last_result"] = (
                        f"✓ Candidate v{candidate} staged at {result.stage_dir}. Live server unchanged."
                    )
                    save_config(config, state)
                    self._redirect()
                    return

                # ---- Apply / Force ----
                if parsed_path in ("/apply", "/force"):
                    force = parsed_path == "/force"
                    form = _form_data(self)
                    candidate = state.get("candidate_version")
                    if not candidate:
                        raise UnsafeArchiveError("No candidate staged. Upload a ZIP first.")
                    confirm = form.get("confirm", "").strip()
                    if force:
                        require_force_confirmation(candidate, confirm)
                    else:
                        if confirm != f"APPLY {candidate}":
                            raise ConfirmationRequired(f"type exactly: APPLY {candidate}")
                    archive = staging / "uploads" / str(state["candidate_archive"])
                    crafty = self._get_crafty()
                    maint = VelocityMaintenanceToggle(velocity_maintenance_config)
                    result = live_apply_archive(
                        archive_path=archive,
                        root=root,
                        staging_root=staging,
                        backup_root=backup_root,
                        crafty=crafty,
                        maintenance=maint,
                        minimotd_conf=minimotd_conf,
                        candidate_version=candidate,
                        user_protected=state["protected_paths"],
                        force=force,
                        overlay_dir_name=overlay_dir_name,
                    )
                    state.update(
                        installed_version=result.installed_version,
                        installed_version_override=None,
                        candidate_version=None,
                        candidate_archive=None,
                        last_result=result.message,
                    )
                    save_config(config, state)
                    self._redirect()
                    return

                # ---- Protect ----
                if parsed_path == "/protect":
                    form = _form_data(self)
                    path = form.get("path", "").strip()
                    if not path:
                        raise ValueError("No path specified")
                    src = root / path
                    entry_key = path + "/" if src.is_dir() else path

                    # Count total files to show progress for large dirs
                    if src.is_dir():
                        total = sum(1 for _ in src.rglob("*") if _.is_file())
                    else:
                        total = 1

                    # Record job start immediately
                    job = {"path": entry_key, "copied": 0, "total": total,
                           "status": "running", "error_msg": None}
                    state["protect_job"] = job
                    save_config(config, state)

                    def _run_protect(path=path, entry_key=entry_key, total=total):
                        last_write = [0]
                        def _progress(copied, tot):
                            # Only write every 50 files or on the last file to avoid I/O storm
                            if copied == tot or copied - last_write[0] >= 50:
                                last_write[0] = copied
                                s = load_config(config)
                                if s.get("protect_job", {}).get("path") == entry_key:
                                    s["protect_job"]["copied"] = copied
                                    s["protect_job"]["total"] = tot
                                    save_config(config, s)

                        try:
                            protect_path(root, overlay_dir, path, progress_cb=_progress)
                            s = load_config(config)
                            entries = s.get("protected_entries", [])
                            if entry_key not in entries:
                                entries.append(entry_key)
                            s["protected_entries"] = entries
                            s["protect_job"] = {"path": entry_key, "copied": total,
                                                "total": total, "status": "done",
                                                "error_msg": None}
                            s["last_result"] = f"🔒 Protected {total} file(s): {entry_key}"
                            save_config(config, s)
                        except Exception as exc:
                            s = load_config(config)
                            s["protect_job"] = {"path": entry_key, "copied": 0,
                                                "total": total, "status": "error",
                                                "error_msg": str(exc)}
                            s["last_result"] = f"Error protecting {entry_key}: {exc}"
                            save_config(config, s)

                    threading.Thread(target=_run_protect, daemon=True).start()
                    referer = self.headers.get("Referer", "/")
                    self._redirect(referer if referer.startswith("/") else "/")
                    return

                # ---- Unprotect ----
                if parsed_path == "/unprotect":
                    form = _form_data(self)
                    path = form.get("path", "").strip()
                    if not path:
                        raise ValueError("No path specified")
                    unprotect_path(overlay_dir, path)
                    # Remove from entries (match with or without trailing slash)
                    entries = state.get("protected_entries", [])
                    entries = [e for e in entries if e.rstrip("/") != path.rstrip("/")]
                    state["protected_entries"] = entries
                    state["last_result"] = f"🔓 Removed protection for {path}"
                    save_config(config, state)
                    referer = self.headers.get("Referer", "/")
                    self._redirect(referer if referer.startswith("/") else "/")
                    return

                # ---- Manual version override ----
                if parsed_path == "/set-version":
                    form = _form_data(self)
                    raw = form.get("version", "").strip()
                    if not raw:
                        # Empty submission clears the override, reverting to jar auto-detect
                        state["installed_version_override"] = None
                        detected = installed_version(root)
                        state["installed_version"] = detected
                        state["last_result"] = f"✓ Manual version cleared — reverted to detected v{detected}."
                    else:
                        if not VERSION_RE.fullmatch(raw):
                            raise ValueError(
                                f"Invalid version '{raw}'. Use a form like 4.0.3 or 4.0.3hf."
                            )
                        state["installed_version_override"] = raw
                        state["installed_version"] = raw
                        state["last_result"] = f"✓ Current version manually set to v{raw}."
                    save_config(config, state)
                    self._redirect()
                    return

                if parsed_path == "/check":
                    ver = latest_curseforge_version()
                    installed = state.get("installed_version", "unknown")
                    if ver == installed:
                        state["last_result"] = f"✓ Up to date — installed v{installed} matches latest v{ver} on Modrinth."
                    elif ver.startswith("unavailable"):
                        state["last_result"] = f"Could not reach Modrinth: {ver}"
                    else:
                        state["last_result"] = f"Update available: installed v{installed} → latest v{ver} on Modrinth. Download the ZIP and upload below."
                    save_config(config, state)
                    self._redirect()
                    return

                self._send(404, b"not found", "text/plain")

            except (UnsafeArchiveError, ConfirmationRequired, OSError, ValueError, FileNotFoundError) as exc:
                state["last_result"] = f"Error: {exc}"
                save_config(config, state)
                self._send(400, self._render_dashboard(state), "text/html; charset=utf-8")
            except RuntimeError as exc:
                state["last_result"] = f"Error: {exc}"
                save_config(config, state)
                self._send(500, self._render_dashboard(state), "text/html; charset=utf-8")
            except Exception as exc:
                state["last_result"] = f"Unexpected error: {type(exc).__name__}: {exc}"
                save_config(config, state)
                self._send(500, self._render_dashboard(state), "text/html; charset=utf-8")

        def log_message(self, format, *args):
            return

    return Handler


if __name__ == "__main__":
    bind = os.environ.get("PROMINENCE_UPDATER_BIND", "127.0.0.1")
    port = int(os.environ.get("PROMINENCE_UPDATER_PORT", "8789"))
    ThreadingHTTPServer((bind, port), make_handler()).serve_forever()
