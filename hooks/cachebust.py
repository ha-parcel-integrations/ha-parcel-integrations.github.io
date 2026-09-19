"""Stamp a content hash onto every extra_css / extra_javascript URL.

GitHub Pages serves both with ``cache-control: max-age=600`` and their paths
never change between deploys, so for ten minutes after a release a returning
visitor can pair freshly deployed HTML with the stylesheet they cached before
it. The carrier grid lives entirely in that stylesheet — paired with the old
one it renders as an unstyled pile of logos, and the visitor has no way to
know a reload would fix it.

Appending ``?h=<hash of the file>`` makes every change its own URL, so new
HTML can only ever ask for the CSS and JS that shipped with it. A file that
did not change keeps its hash, and therefore keeps being served from cache.

Wired up through ``hooks:`` in mkdocs.yml, so it applies to ``mkdocs serve``
as well — a local preview reloads the stylesheet it just rebuilt.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from mkdocs.config.config_options import ExtraScriptValue

# Eight hex characters is 4 bytes of the digest: plenty to tell two versions
# of the same file apart, and short enough to read in a page source.
HASH_LENGTH = 8


def _stamp(docs_dir: Path, path: str) -> str:
    # Only our own files carry a hash; a CDN URL is left exactly as written.
    if "://" in path or path.startswith("//") or "?" in path:
        return path
    source = docs_dir / path
    if not source.is_file():
        return path
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:HASH_LENGTH]
    return f"{path}?h={digest}"


def on_config(config, **kwargs):
    docs_dir = Path(config["docs_dir"])

    config["extra_css"] = [_stamp(docs_dir, css) for css in config["extra_css"]]

    stamped = []
    for script in config["extra_javascript"]:
        # mkdocs 1.5+ may hand these over as ExtraScriptValue (a str subclass
        # carrying type/async/defer), and rebuilding one from a plain string
        # would drop those attributes.
        if isinstance(script, ExtraScriptValue):
            script.path = _stamp(docs_dir, script.path)
            stamped.append(script)
        else:
            stamped.append(_stamp(docs_dir, script))
    config["extra_javascript"] = stamped

    return config
