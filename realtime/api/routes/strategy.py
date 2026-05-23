"""POST /strategy/simulate — Monte Carlo strategy ranking."""
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class SimulateRequest(BaseModel):
    year: int
    round_number: int
    wet: bool = False
    weather_override: dict | None = None


@router.post("/strategy/simulate")
async def simulate(req: SimulateRequest):
    raise NotImplementedError
