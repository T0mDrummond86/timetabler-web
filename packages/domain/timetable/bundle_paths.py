"""Resolve project assets in development and packaged installs."""
from __future__ import annotations

from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent
_DOMAIN_ROOT = _PKG_ROOT.parent


def project_root() -> Path:
    """Directory containing ``templates/`` and root-level workbook templates."""
    return _DOMAIN_ROOT


def resource_path(*parts: str) -> Path:
    return project_root().joinpath(*parts)
