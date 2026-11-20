from pydantic import BaseModel, Field
class GapInput(BaseModel):
    service: str = Field(min_length=1, max_length=160)
    start_min: float = Field(ge=0, allow_inf_nan=False)
    end_min: float = Field(ge=0, allow_inf_nan=False)
    reason: str = Field(default='', max_length=500)
