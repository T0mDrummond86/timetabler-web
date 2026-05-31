"""URL-safe organization slug."""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from timetable.core.tenancy_models import Organization

_slug_re = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    base = _slug_re.sub("-", name.strip().lower()).strip("-")
    return base[:60] or "org"


def unique_org_slug(db: Session, name: str) -> str:
    base = slugify(name)
    slug = base
    n = 2
    while db.query(Organization).filter(Organization.slug == slug).first() is not None:
        slug = f"{base}-{n}"
        n += 1
    return slug
