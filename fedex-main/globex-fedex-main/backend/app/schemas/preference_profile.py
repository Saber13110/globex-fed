from pydantic import BaseModel, Field


class PreferenceProfileStructured(BaseModel):
    tone: str = Field(default="professional", max_length=32)
    cite_fedex: bool = True
    short_answers: bool = False
    free_notes: str = Field(default="", max_length=300)
