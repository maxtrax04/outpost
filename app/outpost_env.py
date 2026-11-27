"""
An empty setting means its default, the same as a setting that isn't there.

unRAID's container templates pass every variable the template lists, empty or not, and a Compose
.env file can have lines such as `OUTPOST_CONTACT=`, so each script that reads OUTPOST_* settings imports this
first, and an empty (or blank) OUTPOST_* variable is dropped before anything reads it.

Uses only the Python standard library.
"""

import os
from typing import List, MutableMapping, Optional


def forget_empty_settings(environ: Optional[MutableMapping[str, str]] = None) -> List[str]:
    """Drop every empty or blank OUTPOST_* variable; returns their names."""
    environ = os.environ if environ is None else environ
    empty = sorted(name for name, value in environ.items() if name.startswith("OUTPOST_") and not value.strip())
    for name in empty:
        del environ[name]
    return empty


forget_empty_settings()
