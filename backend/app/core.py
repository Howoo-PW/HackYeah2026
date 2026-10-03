"""B1 API endpoints; B2 and AI routers can be mounted alongside this router."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from .auth import User, optional_user, require_admin, require_user
from .database import get_repository
from .errors import AppError
from .geo import parse_bbox, validate_point
from .schemas import (Comment, CommentCreate, CommentPage, ContentUpdate, Dimension,
                      FeatureCollection, GroupDetail, NearestSegment, Profile, Rating, RatingCreate, SegmentDetail)

router = APIRouter()
RepositoryDep = Annotated[object, Depends(get_repository, scope="function")]
UserDep = Annotated[User, Depends(require_user)]
SegmentId = Annotated[int, Path(ge=1, le=2147483647)]


@router.get("/me", response_model=Profile, tags=["auth"])
def me(user: UserDep, repo: RepositoryDep):
    """Return the signed-in user's profile and trusted role."""
    return repo.profile(user)


@router.get("/segments", response_model=FeatureCollection, tags=["segments"])
def segments(repo: RepositoryDep, bbox: str, dimension: Dimension | None = None,
             min_score: Annotated[float | None, Query(ge=1, le=5)] = None, rated_only: bool = False):
    """Return GeoJSON roads intersecting the requested Krakow bounding box."""
    if min_score is not None and dimension is None:
        raise AppError(422, "VALIDATION_ERROR", "min_score wymaga dimension")
    return repo.segments(parse_bbox(bbox), dimension, min_score, rated_only)


@router.get("/segments/nearest", response_model=NearestSegment, tags=["segments"])
def nearest(repo: RepositoryDep, lat: float, lon: float):
    """Find the closest road no more than 50 metres from a Krakow location."""
    validate_point(lat, lon)
    return repo.nearest(lat, lon)


@router.get("/groups/{group_id}", response_model=GroupDetail, tags=["segments"])
def group(group_id: SegmentId, repo: RepositoryDep):
    """Return a street stretch (group of segments) with merged geometry and group scores."""
    return repo.group(group_id)


@router.get("/segments/{segment_id}", response_model=SegmentDetail, tags=["segments"])
def segment(segment_id: SegmentId, repo: RepositoryDep, user: Annotated[User | None, Depends(optional_user)]):
    """Return road details and today's rating for an optional signed-in user."""
    return repo.segment(segment_id, user.id if user else None)


@router.post("/segments/{segment_id}/ratings", response_model=Rating, status_code=201, responses={200: {"model": Rating}}, tags=["ratings"])
def rate(segment_id: SegmentId, payload: RatingCreate, user: UserDep,
         repo: RepositoryDep, request: Request, response: Response):
    """Create or replace today's score under the 30-attempt hourly user limit."""
    request.app.state.rate_limiter.check(str(user.id), "ratings", 30)
    result, created = repo.rate(segment_id, user.id, payload, datetime.now(timezone.utc))
    response.status_code = 201 if created else 200
    return result


@router.get("/segments/{segment_id}/comments", response_model=CommentPage, tags=["comments"])
def comments(segment_id: SegmentId, repo: RepositoryDep,
             page: Annotated[int, Query(ge=1)] = 1,
             page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    """Return a page of visible comments, newest first."""
    return repo.comments(segment_id, page, page_size)


@router.post("/segments/{segment_id}/comments", response_model=Comment, status_code=201, tags=["comments"])
def comment(segment_id: SegmentId, payload: CommentCreate, user: UserDep,
            repo: RepositoryDep, request: Request):
    """Create a verified user's comment under the 10-attempt hourly limit."""
    request.app.state.rate_limiter.check(str(user.id), "comments", 10)
    return repo.comment(segment_id, user.id, payload.text)


@router.patch("/admin/comments/{comment_id}", response_model=Comment, tags=["admin"])
def moderate_comment(comment_id: UUID, payload: ContentUpdate,
                     admin: Annotated[User, Depends(require_admin)], repo: RepositoryDep):
    """Allow only an administrator to hide or restore a comment."""
    return repo.moderate_comment(comment_id, payload.status)
