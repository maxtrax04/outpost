#!/usr/bin/env python3
"""
Publishes the Home Assistant add-on (homeassistant/) into a checkout of the add-on repository
(maxtrax04/outpost-addon), with the add-on's version set to the release. The release workflow
runs it for every version tag: betas go to that repository's beta branch, and released versions
to both its main and beta branches (.github/workflows/release.yml).

  python3 scripts/publish_addon.py 0.7.0 path/to/outpost-addon

Everything in the target except .git is replaced, so files removed here go there too.
"""

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "homeassistant"
VERSION_PATTERN = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?")


def publish(version: str, target: Path, source: Path = SOURCE, changelog: Path = ROOT / "CHANGELOG.md") -> None:
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"not a version: {version!r}")
    target.mkdir(parents=True, exist_ok=True)
    for item in target.iterdir():
        if item.name == ".git":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    for item in source.iterdir():
        if item.is_dir():
            shutil.copytree(item, target / item.name)
        else:
            shutil.copy2(item, target / item.name)

    config_path = target / "outpost" / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["version"] = version
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # The store's Changelog tab: Outpost's own changelog
    shutil.copy2(changelog, target / "outpost" / "CHANGELOG.md")


def main(argv: list) -> int:
    if len(argv) != 3:
        print("usage: publish_addon.py <version> <add-on repository folder>", file=sys.stderr)
        return 2
    publish(argv[1], Path(argv[2]))
    print(f"Add-on {argv[1]} written to {argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
