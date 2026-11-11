#!/usr/bin/env python3
"""
Outpost community themes: downloads the themes listed in OUTPOST_COMMUNITY_THEMES from the
community themes repository, once, when the container starts.

    OUTPOST_COMMUNITY_THEMES=maxtrax04/weather-desk,maxtrax04/wristcomp

Each theme is named <username>/<theme>, like its folder in the repository. The downloaded copies
are kept in /data/community/themes, so they survive restarts and keep working with no internet.
Nothing else in Outpost waits for this: when a download fails, the copies from before are used
and one warning is logged. Themes that are no longer listed are removed.

Only theme files are kept (CSS, fonts, and images, the same types nginx serves for themes).
Uses only Python's standard library.
"""

import io
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

REPOSITORY = "maxtrax04/outpost-themes"
ARCHIVE_URL = "https://codeload.github.com/{repository}/tar.gz/{ref}"
DEFAULT_REF = "main"

# Downloaded themes, served by nginx under /themes/ (see nginx/default.conf).
# The folder above it (/data/community) is not served directly.
COMMUNITY_DIR = Path("/data/community/themes")

NAME = r"[a-z0-9-]+"
THEME_ID = rf"{NAME}/{NAME}"
THEME_FILE = "theme.css"
# One part of a file path inside a theme, and the file types kept (both match nginx/default.conf)
PATH_PART = r"[A-Za-z0-9_-][A-Za-z0-9._-]*"
FILE_TYPES = {"css", "woff2", "woff", "ttf", "otf", "png", "jpg", "jpeg", "gif", "webp", "avif", "svg"}

MAX_THEMES = 50
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_FILE_BYTES = 5 * 1024 * 1024
TIMEOUT_SECONDS = 20


def log(message: str) -> None:
    print(f"[Outpost] {message}", flush=True)


def warn(message: str) -> None:
    print(f"[Outpost] {message}", file=sys.stderr, flush=True)


def read_version() -> str:
    here = Path(__file__).resolve().parent
    for candidate in (here / "VERSION", here.parent / "VERSION"):
        try:
            version = candidate.read_text(encoding="utf-8").strip()
            if version:
                return version
        except OSError:
            continue
    return "dev"


def wanted_themes(value: str) -> Tuple[List[str], List[str]]:
    """
    The theme ids in OUTPOST_COMMUNITY_THEMES (separated by commas or spaces), and a warning for
    each entry that cannot be used.
    """
    ids: List[str] = []
    problems: List[str] = []
    for entry in re.split(r"[\s,]+", value.strip().lower()):
        if not entry:
            continue
        if not re.fullmatch(THEME_ID, entry):
            problems.append(f"Ignoring community theme '{entry}': use <username>/<theme>, "
                            "for example maxtrax04/weather-desk")
        elif entry not in ids:
            ids.append(entry)
    if len(ids) > MAX_THEMES:
        problems.append(f"Only the first {MAX_THEMES} community themes are used")
        ids = ids[:MAX_THEMES]
    return ids, problems


def ref_setting(value: str) -> Optional[str]:
    """OUTPOST_COMMUNITY_THEMES_REF: a branch, tag, or commit (default main); None if unusable."""
    value = value.strip()
    if not value:
        return DEFAULT_REF
    if re.fullmatch(r"[A-Za-z0-9._/-]{1,100}", value) and ".." not in value and not value.startswith("/"):
        return value
    return None


def download(url: str, user_agent: str, limit: int = MAX_ARCHIVE_BYTES) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"the download is larger than {limit // (1024 * 1024)} MB")
    return data


def theme_file_path(parts: List[str]) -> Optional[Path]:
    """The path of a file inside a theme folder, or None if it is not a theme file Outpost serves."""
    if not parts or not all(re.fullmatch(PATH_PART, part) for part in parts):
        return None
    if parts[-1].rsplit(".", 1)[-1].lower() not in FILE_TYPES or "." not in parts[-1]:
        return None
    return Path(*parts)


def extract(archive: bytes, wanted: Set[str], destination: Path) -> Set[str]:
    """
    Writes the files of the wanted themes from a repository archive into destination/<id>/, and
    returns the ids found with a theme.css. Links, other file types, and odd paths are skipped.
    """
    found: Set[str] = set()
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        for member in tar:
            # <repository>-<ref>/<username>/<theme>/<file...>
            parts = member.name.split("/")
            if not member.isfile() or len(parts) < 4:
                continue
            theme_id = f"{parts[1]}/{parts[2]}"
            if theme_id not in wanted or member.size > MAX_FILE_BYTES:
                continue
            relative = theme_file_path(parts[3:])
            if relative is None:
                continue
            source = tar.extractfile(member)
            if source is None:
                continue
            target = destination / parts[1] / parts[2] / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read(MAX_FILE_BYTES + 1)[:MAX_FILE_BYTES])
            if relative == Path(THEME_FILE):
                found.add(theme_id)
    return found


def installed_themes(root: Path) -> List[str]:
    if not root.is_dir():
        return []
    return sorted(
        f"{user.name}/{theme.name}"
        for user in root.iterdir() if user.is_dir() and re.fullmatch(NAME, user.name)
        for theme in user.iterdir() if theme.is_dir() and re.fullmatch(NAME, theme.name)
    )


def delete(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def remove_unlisted(root: Path, wanted: Set[str]) -> List[str]:
    """Removes downloaded themes that are no longer listed, and anything else in the folder."""
    removed: List[str] = []
    if not root.is_dir():
        return removed
    for user in list(root.iterdir()):
        if not user.is_dir() or not re.fullmatch(NAME, user.name):
            delete(user)
            continue
        for theme in list(user.iterdir()):
            if f"{user.name}/{theme.name}" not in wanted:
                delete(theme)
                if re.fullmatch(NAME, theme.name):
                    removed.append(f"{user.name}/{theme.name}")
        if not any(user.iterdir()):
            user.rmdir()
    return sorted(removed)


def install(staging: Path, theme_ids: Set[str], root: Path) -> None:
    """Moves each downloaded theme into place, replacing the old copy only once the new one is complete."""
    for theme_id in sorted(theme_ids):
        user, name = theme_id.split("/")
        target = root / user / name
        target.parent.mkdir(parents=True, exist_ok=True)
        old = None
        if target.exists():
            old = staging / f".old-{user}-{name}"
            target.rename(old)
        (staging / user / name).rename(target)
        if old is not None:
            shutil.rmtree(old, ignore_errors=True)


def update(env: Dict[str, str], root: Path = COMMUNITY_DIR, fetch=download) -> int:
    """Brings the downloaded themes in line with the settings. Returns 0, or 1 if a download failed."""
    ids, problems = wanted_themes(env.get("OUTPOST_COMMUNITY_THEMES", ""))
    for problem in problems:
        warn(problem)

    # Leftovers from a download that was interrupted (the container stopped part way)
    if root.parent.is_dir():
        for leftover in root.parent.glob(".download-*"):
            delete(leftover)

    removed = remove_unlisted(root, set(ids))
    if removed:
        log(f"Removed community themes that are no longer listed: {', '.join(removed)}")
    if not ids:
        return 0

    ref = ref_setting(env.get("OUTPOST_COMMUNITY_THEMES_REF", ""))
    if ref is None:
        warn(f"Invalid OUTPOST_COMMUNITY_THEMES_REF; using {DEFAULT_REF}")
        ref = DEFAULT_REF

    url = ARCHIVE_URL.format(repository=REPOSITORY, ref=ref)
    # Only the version: the contact details in Outpost's weather User-Agent are not sent here
    user_agent = f"Outpost/{read_version()}"
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".download-", dir=root.parent))
    try:
        try:
            found = extract(fetch(url, user_agent), set(ids), staging)
        except (urllib.error.URLError, OSError, tarfile.TarError, ValueError, EOFError) as error:
            have = [theme_id for theme_id in ids if theme_id in installed_themes(root)]
            reason = getattr(error, "reason", None) or error
            if have:
                warn(f"Could not download community themes ({reason}); using the copies from before: {', '.join(have)}")
            else:
                warn(f"Could not download community themes ({reason}); they are not available until a download works")
            return 1

        install(staging, found, root)
        if found:
            log(f"Community themes ({REPOSITORY}, {ref}): {', '.join(sorted(found))}")
        missing = [theme_id for theme_id in ids if theme_id not in found]
        if missing:
            kept = [theme_id for theme_id in missing if theme_id in installed_themes(root)]
            note = f"; using the copies from before: {', '.join(kept)}" if kept else ""
            warn(f"Not found in {REPOSITORY} ({ref}): {', '.join(missing)}. "
                 f"Check the spelling: <username>/<theme>, all lowercase{note}")
        return 0
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main() -> int:
    try:
        return update(dict(os.environ))
    except Exception as error:  # never stop the container from starting
        warn(f"Community themes were not updated: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
