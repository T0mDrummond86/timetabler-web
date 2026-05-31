"""Organization routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from timetable.core.tenancy_models import Membership, Organization

from ..auth.deps import get_auth_context, get_current_user, require_editor
from ..database import get_db
from ..schemas import OrganizationCreate, OrganizationOut
from ..util import unique_org_slug

router = APIRouter(prefix="/orgs", tags=["organizations"])


@router.get("", response_model=list[OrganizationOut])
def list_orgs(
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(Membership, Organization)
        .join(Organization, Organization.id == Membership.organization_id)
        .filter(Membership.user_id == user.id)
        .order_by(Organization.name)
        .all()
    )
    return [
        OrganizationOut(id=org.id, name=org.name, slug=org.slug, role=m.role)
        for m, org in rows
    ]


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED)
def create_org(
    body: OrganizationCreate,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    org = Organization(name=body.name.strip(), slug=unique_org_slug(db, body.name))
    db.add(org)
    db.flush()
    m = Membership(user_id=user.id, organization_id=org.id, role="owner")
    db.add(m)
    db.commit()
    db.refresh(org)
    return OrganizationOut(id=org.id, name=org.name, slug=org.slug, role=m.role)


@router.get("/current", response_model=OrganizationOut)
def current_org(ctx=Depends(get_auth_context)):
    return OrganizationOut(
        id=ctx.organization.id,
        name=ctx.organization.name,
        slug=ctx.organization.slug,
        role=ctx.membership.role,
    )
