from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.help import HelpArticle, HelpArticleSummary, HelpContactOption, HelpMetricsResponse, HelpResourceItem
from app.services.help_articles_service import get_help_article, list_help_articles
from app.services.help_center_service import get_contact_options, get_help_metrics, get_help_resources

router = APIRouter(prefix="/help", tags=["help"])


@router.get("/resources", response_model=list[HelpResourceItem])
def list_help_resources(
    lang: str | None = Query(default=None, max_length=8),
) -> list[HelpResourceItem]:
    return [HelpResourceItem.model_validate(r) for r in get_help_resources(lang)]


@router.get("/metrics", response_model=HelpMetricsResponse)
def help_metrics(db: Session = Depends(get_db)) -> HelpMetricsResponse:
    return HelpMetricsResponse.model_validate(get_help_metrics(db))


@router.get("/contact-options", response_model=list[HelpContactOption])
def help_contact_options() -> list[HelpContactOption]:
    return [HelpContactOption.model_validate(o) for o in get_contact_options()]


@router.get("/articles", response_model=list[HelpArticleSummary])
def help_articles(
    lang: str | None = Query(default=None, max_length=8),
) -> list[HelpArticleSummary]:
    return list_help_articles(lang)


@router.get("/articles/{slug}", response_model=HelpArticle)
def help_article_detail(
    slug: str,
    lang: str | None = Query(default=None, max_length=8),
) -> HelpArticle:
    article = get_help_article(slug, lang)
    if article is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return article
