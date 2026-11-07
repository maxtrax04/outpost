#!/usr/bin/env python3
"""
Security headers for Outpost's web server.

Writes an nginx snippet with the Content-Security-Policy and other hardening headers. It runs at
image build time (so the image always has a working file) and again at startup, so the
OUTPOST_FRAME_ANCESTORS setting can change which sites may show Outpost in a frame.

The policy only lets the dashboard load files from Outpost itself. That includes themes: a theme's
CSS cannot pull fonts or images from another site. See SECURITY.md for the exceptions planned for
later features.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

HEADERS_PATH = Path("/etc/nginx/outpost/security-headers.conf")

DEFAULT_FRAME_ANCESTORS = "'self'"

# One allowed frame-ancestors source: a keyword, *, or a scheme and host with an optional port,
# such as http://homeassistant.local:8123 or https://*.example.com
SOURCE_PATTERN = re.compile(
    r"'self'|'none'|\*|https?://(?:\*\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*(?::\d{1,5})?"
)


def parse_frame_ancestors(value: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    Turns the OUTPOST_FRAME_ANCESTORS setting into a frame-ancestors value.

    Returns (value, warning). Sources are separated by spaces or commas; self and none may be
    written with or without quotes. Anything that is not a plain source is rejected, because
    the value goes into an HTTP header.
    """
    text = (value or "").strip()
    if not text:
        return DEFAULT_FRAME_ANCESTORS, None

    sources: List[str] = []
    for token in re.split(r"[\s,]+", text):
        if token.lower() in ("self", "'self'"):
            token = "'self'"
        elif token.lower() in ("none", "'none'"):
            token = "'none'"
        else:
            token = token.rstrip("/")
        if not SOURCE_PATTERN.fullmatch(token):
            return DEFAULT_FRAME_ANCESTORS, (
                f"Invalid OUTPOST_FRAME_ANCESTORS entry {token!r}; use addresses like "
                f"http://homeassistant.local:8123. Using {DEFAULT_FRAME_ANCESTORS}"
            )
        if token not in sources:
            sources.append(token)

    if "'none'" in sources and len(sources) > 1:
        return DEFAULT_FRAME_ANCESTORS, (
            f"OUTPOST_FRAME_ANCESTORS cannot combine none with other entries. Using {DEFAULT_FRAME_ANCESTORS}"
        )
    return " ".join(sources), None


def content_security_policy(frame_ancestors: str = DEFAULT_FRAME_ANCESTORS) -> str:
    """Everything the dashboard needs comes from Outpost itself, so nothing else is allowed."""
    directives = [
        "default-src 'none'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self'",
        "font-src 'self'",
        "connect-src 'self'",
        "manifest-src 'self'",
        "base-uri 'none'",
        "form-action 'none'",
        f"frame-ancestors {frame_ancestors}",
    ]
    return "; ".join(directives)


def nginx_snippet(frame_ancestors: str = DEFAULT_FRAME_ANCESTORS) -> str:
    # "always" also adds the headers to error pages
    return (
        "# Written by /app/outpost_web.py at startup; edits here are overwritten.\n"
        "# Included in the server block and in every location that sets its own headers,\n"
        "# because nginx drops inherited add_header lines in a location that has any.\n"
        f'add_header Content-Security-Policy "{content_security_policy(frame_ancestors)}" always;\n'
        'add_header X-Content-Type-Options "nosniff" always;\n'
        'add_header Referrer-Policy "no-referrer" always;\n'
    )


def write_headers(path: Path = HEADERS_PATH, setting: Optional[str] = None) -> str:
    """Writes the snippet and returns the frame-ancestors value used."""
    frame_ancestors, warning = parse_frame_ancestors(setting)
    if warning:
        print(f"[Outpost] {warning}", file=sys.stderr, flush=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(nginx_snippet(frame_ancestors), encoding="utf-8")
    temp.replace(path)
    return frame_ancestors


if __name__ == "__main__":
    used = write_headers(setting=os.getenv("OUTPOST_FRAME_ANCESTORS"))
    print(f"[Outpost] Security headers written. Pages may be framed by: {used}", flush=True)
