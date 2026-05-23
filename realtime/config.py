import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://airflow:airflow@localhost:5432/f1")
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
FASTF1_CACHE_DIR: str = os.getenv("FASTF1_CACHE_DIR", "./cache")
OPEN_METEO_URL: str = os.getenv("OPEN_METEO_URL", "https://api.open-meteo.com/v1/forecast")

# undercut-f1 sidecar (Fase 2) — .NET service exposing F1 SignalR via REST/Swagger
UNDERCUT_URL: str = os.getenv("UNDERCUT_URL", "http://localhost:5000")
