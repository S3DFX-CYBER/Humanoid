"""Document templates for the render service."""

import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

DEFAULT_TEMPLATE: dict = {
    "page": {
        "size": "letter",
        "margins": {"top": 1, "bottom": 1, "left": 1, "right": 1},
    },
    "fonts": {
        "body": "Times New Roman",
        "bodySize": 12,
        "heading": "Times New Roman",
        "headingSize": 14,
    },
    "spacing": {"lineSpacing": 2.0, "paragraphSpacing": 0},
    "titlePage": {"enabled": True, "fields": ["title"]},
    "toc": {"enabled": False, "depth": 2},
    "headers": {"enabled": False, "includePageNumber": False},
}


def _merge(base: dict, override: dict) -> dict:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


@lru_cache(maxsize=16)
def load_template(name: str = "default") -> dict:
    """Load ``templates/<name>.json``, falling back to built-in defaults."""
    path = TEMPLATE_DIR / f"{name}.json"
    if not path.exists():
        logger.warning("[render] template %r not found, using defaults", name)
        return DEFAULT_TEMPLATE

    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("[render] template %r unreadable: %s", name, exc)
        return DEFAULT_TEMPLATE

    return _merge(DEFAULT_TEMPLATE, data)
