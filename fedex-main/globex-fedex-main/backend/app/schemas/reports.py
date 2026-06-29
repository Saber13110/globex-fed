from datetime import datetime

from pydantic import BaseModel, Field


class ReportKpiItem(BaseModel):
    key: str
    label: str
    value: float
    display_value: str
    trend_percent: float
    trend_up: bool
    sparkline: list[float]


class ReportsKpisResponse(BaseModel):
    items: list[ReportKpiItem]
    period_from: datetime
    period_to: datetime


class ChartPoint(BaseModel):
    name: str
    value: float


class ReportsChartsResponse(BaseModel):
    shipments_trend: list[ChartPoint]
    delivery_performance: list[ChartPoint]
    delayed_shipments: list[ChartPoint]
    country_statistics: list[ChartPoint]


class ReportCatalogItem(BaseModel):
    slug: str
    name: str
    description: str
    category: str
    default_format: str
    period: str
    last_run_id: int | None = None
    last_status: str | None = None
    last_created_at: datetime | None = None
    generated_by_name: str | None = None


class ReportRunRead(BaseModel):
    id: int
    slug: str
    name: str
    category: str
    format: str
    period_label: str
    status: str
    file_size: int
    row_count: int
    generated_by_name: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ReportListResponse(BaseModel):
    items: list[ReportCatalogItem]
    runs: list[ReportRunRead]
    total: int
    page: int
    page_size: int


class ReportGenerateRequest(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    format: str = Field(default="xlsx", pattern="^(xlsx|csv|json|pdf)$")
    date_from: str | None = None
    date_to: str | None = None


class ReportGenerateResponse(BaseModel):
    run: ReportRunRead
    download_url: str


class ReportScheduleRead(BaseModel):
    id: int
    name: str
    slug: str
    frequency: str
    run_time: str
    recipients: str
    format: str
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(min_length=1, max_length=64)
    frequency: str = Field(pattern="^(daily|weekly|monthly)$")
    run_time: str = Field(default="08:00", max_length=8)
    recipients: str = Field(default="", max_length=500)
    format: str = Field(default="xlsx", max_length=16)


class ReportAiRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)


class ReportAiResponse(BaseModel):
    reply: str
    suggested_slug: str | None = None
    run: ReportRunRead | None = None
    download_url: str | None = None


class ReportPreviewResponse(BaseModel):
    columns: list[str]
    rows: list[list[str]]
    total_rows: int


class ReportShareRequest(BaseModel):
    recipients: str = Field(default="", max_length=500)
    confirm: bool = False


class ReportShareResponse(BaseModel):
    share_url: str = ""
    message: str
    sent_to: list[str] = Field(default_factory=list)
    pending_confirmation: bool = False
