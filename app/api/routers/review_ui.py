from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates


templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parents[1] / "templates")
)
router = APIRouter(tags=["review-ui"])


@router.get("/review", include_in_schema=False)
def review_home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="review.html",
        context={},
    )
