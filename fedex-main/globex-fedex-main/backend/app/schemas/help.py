from pydantic import BaseModel, Field


class HelpResourceItem(BaseModel):
    id: str
    title: str
    description: str
    articlesCount: int = Field(..., ge=0)
    readTime: str
    category: str


class HelpMetricsResponse(BaseModel):
    averageResponse: str
    resolutionRate: str
    ticketsSolved: int = Field(..., ge=0)
    satisfaction: str
    supportOnline: bool


class HelpContactOption(BaseModel):
    id: str
    title: str
    description: str
    status: str
    cta: str
    action: str


class HelpArticleStep(BaseModel):
    title: str
    body: str


class HelpArticleFaqItem(BaseModel):
    question: str
    answer: str


class HelpArticleSection(BaseModel):
    type: str = "paragraph"
    heading: str | None = None
    body: str | None = None
    items: list[str] | None = None
    steps: list[HelpArticleStep] | None = None
    faq: list[HelpArticleFaqItem] | None = None


class HelpArticleSummary(BaseModel):
    id: str
    slug: str
    title: str
    category: str
    summary: str
    readTime: str
    updatedAt: str


class HelpArticle(HelpArticleSummary):
    sections: list[HelpArticleSection] = Field(default_factory=list)
    relatedSlugs: list[str] = Field(default_factory=list)
