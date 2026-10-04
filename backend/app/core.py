"""B1 API endpoints; B2 and AI routers can be mounted alongside this router."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Path, Query, Request, Response, UploadFile

from .auth import User, optional_user, require_admin, require_user
from . import photos as photo_store
from . import embeddings, summaries
from .database import get_repository
from .errors import AppError
from .geo import clamp_bbox, parse_bbox, validate_point
from .schemas import (Comment, CommentCreate, CommentPage, ContentUpdate, Dimension,
                      FeatureCollection, GroupDetail, GroupMapCollection, MyOpinion, NearestSegment, Photo, PhotoPage, Profile, Street, Summary, Rating, RatingCreate, SegmentDetail)

router = APIRouter()
RepositoryDep = Annotated[object, Depends(get_repository, scope="function")]
UserDep = Annotated[User, Depends(require_user)]
SegmentId = Annotated[int, Path(ge=1, le=2147483647)]


@router.get("/me", response_model=Profile, tags=["auth"])
def me(user: UserDep, repo: RepositoryDep):
    """Return the signed-in user's profile and trusted role."""
    return repo.profile(user)


@router.get("/me/opinions", response_model=list[MyOpinion], tags=["auth"])
def my_opinions(user: UserDep, repo: RepositoryDep):
    """Return the signed-in user's own ratings and comments, newest first (max 100)."""
    return repo.my_opinions(user.id)


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


@router.get("/groups", response_model=GroupMapCollection, tags=["segments"])
def groups_map(repo: RepositoryDep, bbox: str, dimension: Dimension | None = None,
               min_score: Annotated[float | None, Query(ge=1, le=5)] = None, rated_only: bool = False):
    """Fragments (300-700 m) with merged geometry and scores for zoomed-out map views."""
    if min_score is not None and dimension is None:
        raise AppError(422, "VALIDATION_ERROR", "min_score wymaga dimension")
    area = clamp_bbox(bbox)
    if area is None:
        return {"type": "FeatureCollection", "features": []}
    return repo.group_map(area, dimension, min_score, rated_only)


@router.get("/segments/{segment_id}/street", response_model=Street, tags=["segments"])
def street(segment_id: SegmentId, repo: RepositoryDep):
    """Ids of all roads of the clicked road's whole street (same name, joined end to end), for highlighting it on the map. Not in the contract yet."""
    return repo.street(segment_id)


@router.get("/groups/{group_id}", response_model=GroupDetail, tags=["segments"])
def group(group_id: SegmentId, repo: RepositoryDep):
    """Return a street stretch (group of segments) with merged geometry and group scores."""
    return repo.group(group_id)


@router.get("/segments/{segment_id}", response_model=SegmentDetail, tags=["segments"])
def segment(segment_id: SegmentId, repo: RepositoryDep, user: Annotated[User | None, Depends(optional_user)],
            request: Request, background: BackgroundTasks):
    """Return road details and the signed-in user's own rating, comment and photo; starts a due AI summary in the background."""
    detail = repo.segment(segment_id, user.id if user else None)
    if detail.get("my_photo"):
        detail["my_photo"] = photo_store.with_urls([detail["my_photo"]])[0]
    if detail["summary_pending"]:
        background.add_task(summaries.refresh, request.app.state.db_pool, segment_id)
    return detail


@router.post("/segments/{segment_id}/ratings", response_model=Rating, status_code=201, responses={200: {"model": Rating}}, tags=["ratings"])
def rate(segment_id: SegmentId, payload: RatingCreate, user: UserDep,
         repo: RepositoryDep, request: Request, response: Response):
    """Create the user's rating of this road or replace the previous one (any day) under the 30-attempt hourly user limit."""
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
            repo: RepositoryDep, request: Request, background: BackgroundTasks):
    """Create a verified user's comment under the 10-attempt hourly limit; its embedding (search by meaning) is made in the background."""
    request.app.state.rate_limiter.check(str(user.id), "comments", 10)
    created = repo.comment(segment_id, user.id, payload.text)
    if getattr(request.app.state, "db_pool", None) is not None:
        background.add_task(embeddings.index_comment, request.app.state.db_pool, created["id"])
    return created


@router.put("/segments/{segment_id}/comments/mine", response_model=Comment, status_code=201, responses={200: {"model": Comment}}, tags=["comments"])
def put_my_comment(segment_id: SegmentId, payload: CommentCreate, user: UserDep,
                   repo: RepositoryDep, request: Request, background: BackgroundTasks, response: Response):
    """Write the user's comment on this road, replacing the previous one (201 first / 200 replaced); re-embedded in the background."""
    request.app.state.rate_limiter.check(str(user.id), "comments", 10)
    result, created = repo.put_comment(segment_id, user.id, payload.text)
    response.status_code = 201 if created else 200
    if getattr(request.app.state, "db_pool", None) is not None:
        background.add_task(embeddings.index_comment, request.app.state.db_pool, result["id"])
    return result


@router.delete("/segments/{segment_id}/comments/mine", status_code=204, tags=["comments"])
def delete_my_comment(segment_id: SegmentId, user: UserDep, repo: RepositoryDep):
    """Remove the user's own comment on this road."""
    repo.delete_my_comments(segment_id, user.id)
    return Response(status_code=204)


@router.patch("/admin/comments/{comment_id}", response_model=Comment, tags=["admin"])
def moderate_comment(comment_id: UUID, payload: ContentUpdate,
                     admin: Annotated[User, Depends(require_admin)], repo: RepositoryDep):
    """Allow only an administrator to hide or restore a comment."""
    return repo.moderate_comment(comment_id, payload.status)


@router.get("/segments/{segment_id}/photos", response_model=PhotoPage, tags=["photos"])
def photos(segment_id: SegmentId, repo: RepositoryDep,
           page: Annotated[int, Query(ge=1)] = 1,
           page_size: Annotated[int, Query(ge=1, le=100)] = 20):
    """Return a page of visible photos with signed URLs (valid one hour), newest first."""
    result = repo.photos(segment_id, page, page_size)
    return {**result, "items": photo_store.with_urls(result["items"])}


@router.post("/segments/{segment_id}/photos", response_model=Photo, status_code=201, tags=["photos"])
def add_photo(segment_id: SegmentId, user: UserDep, repo: RepositoryDep, request: Request,
              file: Annotated[UploadFile, File()], taken_at: Annotated[datetime | None, Form()] = None):
    """Store a JPEG, PNG or WebP up to 5 MB without EXIF, with a thumbnail, under the 10-attempt hourly limit."""
    request.app.state.rate_limiter.check(str(user.id), "photos", 10)
    repo.require_segment(segment_id)
    data = file.file.read(photo_store.MAX_BYTES + 1)
    image = photo_store.process_image(data)
    path, thumbnail_path = photo_store.new_paths(segment_id, image.extension)
    photo_store.upload(path, image.full, image.content_type)
    try:
        photo_store.upload(thumbnail_path, image.thumbnail, "image/jpeg")
        row = repo.add_photo(segment_id, user.id, path, thumbnail_path, taken_at)
    except Exception:
        photo_store.remove([path, thumbnail_path])
        raise
    return photo_store.with_urls([row])[0]


@router.delete("/segments/{segment_id}/photos/mine", status_code=204, tags=["photos"])
def delete_my_photos(segment_id: SegmentId, user: UserDep, repo: RepositoryDep, keep: Annotated[UUID | None, Query()] = None):
    """Remove the user's own photos on this road (all, or all except the new one given in `keep`), rows and stored files."""
    paths = repo.delete_my_photos(segment_id, user.id, keep)
    if paths:
        photo_store.remove(paths)
    return Response(status_code=204)


@router.patch("/admin/photos/{photo_id}", response_model=Photo, tags=["admin"])
def moderate_photo(photo_id: UUID, payload: ContentUpdate,
                   admin: Annotated[User, Depends(require_admin)], repo: RepositoryDep):
    """Allow only an administrator to hide or restore a photo."""
    return photo_store.with_urls([repo.moderate_photo(photo_id, payload.status)])[0]


@router.post("/admin/summaries/{segment_id}/refresh", response_model=Summary, tags=["admin"])
def refresh_summary(segment_id: SegmentId, admin: Annotated[User, Depends(require_admin)], repo: RepositoryDep, request: Request):
    """Recalculate a road's AI summary now (administrator only); 502 when the AI service fails, 422 under 5 visible comments."""
    repo.require_segment(segment_id)
    return summaries.refresh(request.app.state.db_pool, segment_id, force=True)
