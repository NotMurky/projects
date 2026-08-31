"""Safe primitives for Prominence server-pack updates.

The staging helpers (inspect_zip, stage_archive) never touch the live server.
The live-apply helpers (live_apply_archive, CraftyControl, VelocityMaintenanceToggle)
perform the full update sequence per UPDATE-CONTRACT.md.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
import ssl
import stat
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

BUILTIN_PROTECTED = (
    "importantmods/", "fabric.jar", "server.properties", "variables.txt",
    "world/", "worldnopregen/",
)
MAX_ZIP_MEMBERS = 20_000
MAX_ZIP_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 250

# Paths never restored from the overlay dir (world state is live, not static)
OVERLAY_EXCLUDE_PREFIXES = ("world/", "worldnopregen/")


class UnsafeArchiveError(ValueError):
    """The uploaded archive is unsuitable for extraction."""


class ConfirmationRequired(ValueError):
    """A force operation did not receive its exact, visible confirmation."""


@dataclass(frozen=True)
class UpdatePlan:
    install: list[str]
    excluded: list[str]
    rejected: list[str]


@dataclass(frozen=True)
class DiskPreflight:
    required_bytes: int
    available_bytes: int
    ok: bool


@dataclass(frozen=True)
class StagedArchive:
    stage_dir: Path
    plan: UpdatePlan
    overlay_paths: list[str]
    manifest_path: Path


@dataclass(frozen=True)
class ApplyResult:
    success: bool
    installed_version: str
    backup_dir: Path
    changed_paths: list[str]
    excluded_paths: list[str]
    overlay_paths: list[str]
    message: str


def _normalize(path: str) -> str | None:
    if "\x00" in path:
        return None
    candidate = PurePosixPath(path.replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    normalized = str(candidate)
    return normalized if normalized not in ("", ".") else None


def _protected(path: str, protected: tuple[str, ...]) -> bool:
    return any(path == rule.rstrip("/") or path.startswith(rule.rstrip("/") + "/") for rule in protected)


def build_update_plan(archive_paths: list[str], user_protected: list[str] | None = None) -> UpdatePlan:
    protected = BUILTIN_PROTECTED + tuple(user_protected or [])
    install, excluded, rejected = [], [], []
    for raw_path in archive_paths:
        path = _normalize(raw_path)
        if path is None:
            rejected.append(raw_path)
        elif _protected(path, protected):
            excluded.append(path)
        else:
            install.append(path)
    return UpdatePlan(install=install, excluded=excluded, rejected=rejected)


def inspect_zip(data: bytes, user_protected: list[str] | None = None) -> UpdatePlan:
    """Inspect an untrusted ZIP without extracting it; reject unsafe archives."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            if len(members) > MAX_ZIP_MEMBERS:
                raise UnsafeArchiveError("archive contains too many members")
            total = sum(item.file_size for item in members)
            if total > MAX_ZIP_UNCOMPRESSED_BYTES:
                raise UnsafeArchiveError("archive uncompressed size exceeds policy")
            seen: set[str] = set()
            paths: list[str] = []
            rejected: list[str] = []
            for item in members:
                if item.flag_bits & 0x1:
                    raise UnsafeArchiveError("encrypted archive members are not accepted")
                path = _normalize(item.filename)
                is_symlink = stat.S_ISLNK(item.external_attr >> 16)
                if path is not None and path in seen:
                    raise UnsafeArchiveError(f"duplicate archive member: {path}")
                if path is not None:
                    seen.add(path)
                if item.compress_size and item.file_size / item.compress_size > MAX_ZIP_COMPRESSION_RATIO:
                    raise UnsafeArchiveError("archive compression ratio exceeds policy")
                if path is None or is_symlink:
                    rejected.append(item.filename)
                else:
                    paths.append(path)
    except zipfile.BadZipFile as exc:
        raise UnsafeArchiveError("uploaded file is not a valid ZIP") from exc
    plan = build_update_plan(paths, user_protected)
    return UpdatePlan(plan.install, plan.excluded, rejected + plan.rejected)


def importantmods_overlay_plan(paths: list[str]) -> list[str]:
    """Return safe overlay files to restore after a pack update.

    Accepts any normalized path the admin has placed in the overlay directory,
    excluding live world data which must never be treated as static content.
    """
    allowed = []
    for raw in paths:
        path = _normalize(raw)
        if path and not any(path == p.rstrip("/") or path.startswith(p.rstrip("/") + "/")
                            for p in OVERLAY_EXCLUDE_PREFIXES):
            allowed.append(path)
    return allowed


def derive_candidate_version(filename: str, manifest_version: str | None) -> str:
    """Use a trusted supplied manifest value first, then a conservative filename parse."""
    if manifest_version and re.fullmatch(r"\d+\.\d+\.\d+(?:hf)?", manifest_version):
        return manifest_version
    match = re.search(r"(?:^|[-_v ])(\d+\.\d+\.\d+(?:hf)?)(?:\.zip|$)", filename, re.I)
    return match.group(1) if match else "unknown"


def require_force_confirmation(candidate_version: str, confirmation: str) -> bool:
    expected = f"FORCE UPDATE {candidate_version}"
    if confirmation != expected:
        raise ConfirmationRequired(f"type exactly: {expected}")
    return True


def preflight_disk_space(destination: Path, required_bytes: int) -> DiskPreflight:
    available = shutil.disk_usage(destination).free
    return DiskPreflight(required_bytes=required_bytes, available_bytes=available, ok=available >= required_bytes)


def _safe_destination(root: Path, relative: str) -> Path:
    normalized = _normalize(relative)
    if normalized is None:
        raise UnsafeArchiveError(f"unsafe destination: {relative}")
    candidate = root / normalized
    if os.path.commonpath((str(root.resolve()), str(candidate.resolve()))) != str(root.resolve()):
        raise UnsafeArchiveError(f"destination escapes root: {relative}")
    return candidate


def create_backup_manifest(root: Path, changed_paths: list[str], backup_dir: Path) -> dict:
    """Copy pre-update files to a backup tree and write a rollback manifest."""
    root = root.resolve()
    backup_dir.mkdir(parents=True, exist_ok=False)
    entries = []
    for relative in changed_paths:
        source = _safe_destination(root, relative)
        record = {"path": relative}
        if source.is_file():
            destination = backup_dir / "files" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            record["status"] = "copied"
        elif source.exists():
            destination = backup_dir / "files" / relative
            shutil.copytree(source, destination, symlinks=False)
            record["status"] = "copied"
        else:
            record["status"] = "missing"
        entries.append(record)
    manifest = {"created_at": int(time.time()), "root": str(root), "entries": entries}
    (backup_dir / "rollback-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


def stage_archive(
    archive_path: Path,
    root: Path,
    staging_root: Path,
    user_protected: list[str] | None = None,
    overlay_dir_name: str = "Dontdeleteimportantmods",
) -> StagedArchive:
    """Extract only approved files into a staging directory and overlay custom content.

    Deliberately not a live apply: ``root`` is read only.
    """
    archive_path = archive_path.resolve()
    raw = archive_path.read_bytes()
    plan = inspect_zip(raw, user_protected)
    if plan.rejected:
        raise UnsafeArchiveError("archive has rejected members: " + ", ".join(plan.rejected))
    staging_root.mkdir(parents=True, exist_ok=True)
    required = sum(item.file_size for item in zipfile.ZipFile(io.BytesIO(raw)).infolist() if not item.is_dir()) * 2
    disk = preflight_disk_space(staging_root, required)
    if not disk.ok:
        raise OSError(f"insufficient staging disk space: need {disk.required_bytes}, have {disk.available_bytes}")
    stage_dir = staging_root / f"pack-{int(time.time() * 1000)}"
    stage_dir.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for member in plan.install:
            target = _safe_destination(stage_dir, member)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
    overlay_source = root / overlay_dir_name
    overlay_paths = []
    if overlay_source.is_dir():
        source_paths = [p.relative_to(overlay_source).as_posix() for p in overlay_source.rglob("*") if p.is_file()]
        overlay_paths = importantmods_overlay_plan(source_paths)
        for relative in overlay_paths:
            source = overlay_source / relative
            target = _safe_destination(stage_dir, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    manifest = {
        "archive": archive_path.name, "stage_dir": str(stage_dir), "install": plan.install,
        "excluded": plan.excluded, "overlay_paths": overlay_paths, "live_apply": False,
    }
    manifest_path = stage_dir / "staged-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return StagedArchive(stage_dir=stage_dir, plan=plan, overlay_paths=overlay_paths, manifest_path=manifest_path)


def update_motd(properties_path: Path, installed_version: str) -> None:
    """Set only the MOTD key in a Java properties file."""
    motd = f"motd=Prominence II Hasturian Era v{installed_version}"
    lines = properties_path.read_text().splitlines()
    replaced = False
    output = []
    for line in lines:
        if line.startswith("motd="):
            output.append(motd); replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(motd)
    properties_path.write_text("\n".join(output) + "\n")


def update_minimotd_version(conf_path: Path, version: str) -> None:
    """Update the version string inside MiniMOTD main.conf line2."""
    content = conf_path.read_text()
    new_content = re.sub(
        r'(line2="[^"]*?)V\d+\.\d+\.\d+(?:hf)?([^"]*")',
        lambda m: m.group(1) + f"V{version}" + m.group(2),
        content,
    )
    if new_content == content:
        new_content = re.sub(
            r'(line2="[^"]*?Modded[^"]*?)(</[^>]+>|")',
            lambda m: m.group(1) + f" | V{version}" + m.group(2),
            content,
        )
    if new_content != content:
        tmp = conf_path.with_suffix(".tmp")
        tmp.write_text(new_content)
        os.replace(tmp, conf_path)


class VelocityMaintenanceToggle:
    """Toggle the Maintenance plugin's maintenance-enabled flag in config.yml."""

    def __init__(self, config_path: Path):
        self.config_path = config_path

    def is_enabled(self) -> bool:
        try:
            content = self.config_path.read_text()
            m = re.search(r"^maintenance-enabled:\s*(true|false)", content, re.MULTILINE)
            return m.group(1) == "true" if m else False
        except OSError:
            return False

    def _set(self, value: bool) -> None:
        content = self.config_path.read_text()
        new = re.sub(
            r"^maintenance-enabled:.*$",
            f"maintenance-enabled: {'true' if value else 'false'}",
            content,
            flags=re.MULTILINE,
        )
        if new == content and f"maintenance-enabled: {'true' if value else 'false'}" not in content:
            raise OSError(f"maintenance-enabled key not found in {self.config_path}")
        tmp = self.config_path.with_suffix(".tmp")
        tmp.write_text(new)
        os.replace(tmp, self.config_path)

    def enable(self) -> None:
        self._set(True)

    def disable(self) -> None:
        self._set(False)


class CraftyPlayerGate:
    """Read-only Crafty integration seam."""
    def __init__(self, base_url: str, server_id: str, token: str, transport: Callable | None = None):
        self.base_url = base_url.rstrip("/")
        self.server_id = server_id
        self.token = token
        self.transport = transport or self._http_get_json

    def _http_get_json(self, url: str, headers: dict[str, str]) -> dict:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def player_count(self) -> int:
        payload = self.transport(
            f"{self.base_url}/api/v2/servers/{self.server_id}/stats",
            {"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
        )
        data = payload.get("data", payload)
        for key in ("online", "player_count", "players_online"):
            if key in data:
                return int(data[key])
        players = data.get("players")
        return len(players) if isinstance(players, list) else 0


class CraftyControl:
    """Full Crafty control: stats + restart + health polling."""

    def __init__(self, base_url: str, server_id: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.server_id = server_id
        self.token = token

    def _request(self, method: str, path: str) -> dict:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            self.base_url + path,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def stats(self) -> dict:
        payload = self._request("GET", f"/api/v2/servers/{self.server_id}/stats")
        if payload.get("status") != "ok":
            raise RuntimeError(f"Crafty stats failed: {payload}")
        return payload.get("data", {})

    def player_count(self) -> int:
        data = self.stats()
        online = data.get("online", 0)
        if isinstance(online, str):
            online = int(online) if online.isdigit() else 0
        return int(online)

    def is_running(self) -> bool:
        return bool(self.stats().get("running"))

    def restart(self) -> None:
        payload = self._request("POST", f"/api/v2/servers/{self.server_id}/action/restart_server")
        if payload.get("status") != "ok":
            raise RuntimeError(f"Crafty restart failed: {payload}")

    def wait_for_running(self, timeout: float = 180.0, interval: float = 6.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.is_running():
                    return
            except Exception:
                pass
            time.sleep(interval)
        raise RuntimeError(f"Server did not come online within {int(timeout)}s")


# ---------------------------------------------------------------------------
# File protection helpers
# ---------------------------------------------------------------------------

def protect_path(root: Path, overlay_dir: Path, relative: str,
                 progress_cb=None) -> list[str]:
    """Copy root/relative into overlay_dir/relative. Returns list of copied paths.

    Optional ``progress_cb(copied: int, total: int)`` is called after each file.
    """
    normalized = _normalize(relative.rstrip("/"))
    if normalized is None:
        raise UnsafeArchiveError(f"unsafe path: {relative}")
    src = root / normalized
    if not src.exists():
        raise FileNotFoundError(f"not found in server root: {normalized}")
    dst = overlay_dir / normalized
    if os.path.commonpath((str(overlay_dir.resolve()), str(dst.resolve()))) != str(overlay_dir.resolve()):
        raise UnsafeArchiveError("destination escapes overlay directory")
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if progress_cb:
            progress_cb(1, 1)
        return [normalized]
    else:
        # Collect all files first so we know the total
        all_files = [f for f in src.rglob("*") if f.is_file()]
        total = len(all_files)
        copied = []
        for i, src_file in enumerate(all_files, 1):
            rel_to_src = src_file.relative_to(src)
            dst_file = dst / rel_to_src
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied.append((dst / rel_to_src).relative_to(overlay_dir).as_posix())
            if progress_cb:
                progress_cb(i, total)
        return copied


def unprotect_path(overlay_dir: Path, relative: str) -> None:
    """Remove overlay_dir/relative, cleaning up empty parent directories."""
    normalized = _normalize(relative.rstrip("/"))
    if normalized is None:
        raise UnsafeArchiveError(f"unsafe path: {relative}")
    target = overlay_dir / normalized
    if os.path.commonpath((str(overlay_dir.resolve()), str(target.resolve()))) != str(overlay_dir.resolve()):
        raise UnsafeArchiveError("path escapes overlay directory")
    if not target.exists():
        return  # already gone
    if target.is_file():
        target.unlink()
    elif target.is_dir():
        # Delete files individually, then clean up empty dirs
        for f in sorted(target.rglob("*"), reverse=True):
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                try:
                    f.rmdir()
                except OSError:
                    pass
        try:
            target.rmdir()
        except OSError:
            pass
    # Clean up empty parent dirs up to overlay_dir
    parent = target.parent
    while parent.resolve() != overlay_dir.resolve():
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def list_server_files(root: Path, rel_path: str | None, overlay_dir_name: str) -> list[dict]:
    """List one level of root/rel_path, marking which entries are protected."""
    base = root.resolve()
    if rel_path:
        normalized = _normalize(rel_path)
        if normalized is None:
            raise ValueError("unsafe path")
        base = (root / normalized).resolve()
    # Safety: must stay under root
    if os.path.commonpath((str(root.resolve()), str(base))) != str(root.resolve()):
        raise ValueError("path escapes server root")
    if not base.is_dir():
        raise NotADirectoryError(f"not a directory: {base}")
    overlay = root / overlay_dir_name
    items = []
    try:
        entries = sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except PermissionError:
        return []
    for entry in entries:
        if entry.name == overlay_dir_name and base == root.resolve():
            continue  # hide the overlay dir from the browser
        rel = entry.relative_to(root).as_posix()
        # Protected if the entry itself OR any ancestor (not root ".") exists in overlay
        protected = False
        check = Path(rel)
        while str(check) != ".":
            candidate = overlay / check
            if candidate.exists():
                protected = True
                break
            check = check.parent
        size = None
        if entry.is_file():
            try:
                size = entry.stat().st_size
            except OSError:
                pass
        items.append({
            "name": entry.name,
            "path": rel,
            "type": "dir" if entry.is_dir() else "file",
            "protected": protected,
            "size": size,
        })
    return items


def list_protected_entries(overlay_dir: Path, entries: list[str]) -> list[dict]:
    """Return display info for the explicitly protected entries list.

    ``entries`` is the list of paths as the user protected them (e.g.
    "mods/crossstitch.jar" or "mods/").  Only entries that still exist in the
    overlay are returned; stale entries are silently skipped.
    """
    items = []
    for raw in entries:
        is_dir = raw.endswith("/")
        normalized = _normalize(raw.rstrip("/"))
        if normalized is None:
            continue
        target = overlay_dir / normalized
        if not target.exists():
            continue
        if target.is_dir():
            count = sum(1 for _ in target.rglob("*") if _.is_file())
            items.append({"path": normalized + "/", "size": None, "count": count, "type": "dir"})
        else:
            try:
                size = target.stat().st_size
            except OSError:
                size = None
            items.append({"path": normalized, "size": size, "count": None, "type": "file"})
    return items


# ---------------------------------------------------------------------------
# Live apply orchestration
# ---------------------------------------------------------------------------

def live_apply_archive(
    archive_path: Path,
    root: Path,
    staging_root: Path,
    backup_root: Path,
    crafty: CraftyControl,
    maintenance: VelocityMaintenanceToggle,
    minimotd_conf: Path | None,
    candidate_version: str,
    user_protected: list[str] | None = None,
    force: bool = False,
    overlay_dir_name: str = "Dontdeleteimportantmods",
) -> ApplyResult:
    """Full live apply per UPDATE-CONTRACT.md.

    1.  Verify zero players (unless force).
    2.  Inspect archive (always enforced).
    3.  Disk preflight.
    4.  Enable Velocity maintenance.
    5.  Create timestamped backup manifest.
    6.  Apply permitted pack files to server root.
    7.  Overlay protected files from overlay_dir_name/.
    8.  Update MiniMOTD version string.
    9.  Restart through Crafty; wait for running.
    10. Health check.
    11. Disable maintenance on success; leave ON on failure.
    """
    archive_path = archive_path.resolve()
    root = root.resolve()

    # Step 1 — player gate
    if not force:
        players = crafty.player_count()
        if players != 0:
            raise RuntimeError(
                f"Cannot apply: {players} player(s) online. "
                "Wait for all players to leave, or use Force Update."
            )

    # Step 2 — archive inspection
    raw = archive_path.read_bytes()
    plan = inspect_zip(raw, user_protected)
    if plan.rejected:
        raise UnsafeArchiveError("archive has rejected members: " + ", ".join(plan.rejected))

    # Step 3 — disk preflight
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        required = sum(i.file_size for i in zf.infolist() if not i.is_dir()) * 2
    disk = preflight_disk_space(root, required)
    if not disk.ok:
        raise OSError(
            f"Insufficient disk space: need {disk.required_bytes:,} bytes, "
            f"have {disk.available_bytes:,} bytes."
        )

    # Step 4 — enable maintenance
    maintenance.enable()

    ts = int(time.time())
    backup_dir = backup_root / f"backup-{ts}"

    try:
        # Step 5 — backup
        create_backup_manifest(root, plan.install, backup_dir)

        # Step 6 — apply pack files
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for member in plan.install:
                target = _safe_destination(root, member)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)

        # Step 7 — overlay protected files
        overlay_source = root / overlay_dir_name
        overlay_paths: list[str] = []
        if overlay_source.is_dir():
            source_paths = [
                p.relative_to(overlay_source).as_posix()
                for p in overlay_source.rglob("*") if p.is_file()
            ]
            overlay_paths = importantmods_overlay_plan(source_paths)
            for relative in overlay_paths:
                src = overlay_source / relative
                dst = _safe_destination(root, relative)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

        # Step 8 — update MiniMOTD
        if minimotd_conf and minimotd_conf.is_file():
            update_minimotd_version(minimotd_conf, candidate_version)

        # Step 9 — restart and wait
        crafty.restart()
        crafty.wait_for_running(timeout=180.0)

        # Step 10 — health check
        crafty.player_count()

    except Exception as exc:
        raise RuntimeError(
            f"Apply failed: {exc}. "
            f"Maintenance is still ON. Backup preserved at {backup_dir}. "
            "Fix the issue and clear maintenance manually."
        ) from exc

    # Step 11 — clear maintenance
    maintenance.disable()

    return ApplyResult(
        success=True,
        installed_version=candidate_version,
        backup_dir=backup_dir,
        changed_paths=plan.install,
        excluded_paths=plan.excluded,
        overlay_paths=overlay_paths,
        message=(
            f"v{candidate_version} applied. "
            f"{len(plan.install)} files updated, {len(plan.excluded)} excluded, "
            f"{len(overlay_paths)} protected files restored. Backup at {backup_dir}."
        ),
    )
