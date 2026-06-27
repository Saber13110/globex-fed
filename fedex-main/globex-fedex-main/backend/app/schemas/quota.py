from pydantic import BaseModel, Field


class QuotaLimitsRead(BaseModel):
    messages_per_day: int | None = None
    trackings_per_day: int | None = None
    exports_per_day: int | None = None


class QuotaUsageRead(BaseModel):
    messages_today: int = 0
    trackings_today: int = 0
    exports_today: int = 0


class UserQuotaStatus(BaseModel):
    limits: QuotaLimitsRead
    usage: QuotaUsageRead
    remaining: QuotaLimitsRead
    exempt: bool = False


class QuotaLimitUpdate(BaseModel):
    """0 = illimité (supprime la limite), >0 = plafond journalier."""

    messages_per_day: int | None = Field(default=None, ge=0, le=100_000)
    trackings_per_day: int | None = Field(default=None, ge=0, le=100_000)
    exports_per_day: int | None = Field(default=None, ge=0, le=100_000)
