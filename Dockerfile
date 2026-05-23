FROM python:3.11-slim

WORKDIR /app

# uv para instalação rápida de deps
RUN pip install --no-cache-dir uv

# Instala deps antes de copiar código (camada cacheável)
COPY pyproject.toml .
RUN uv pip install --system -e ".[dev]"

COPY . .

EXPOSE 8081

CMD ["uvicorn", "realtime.api.main:app", "--host", "0.0.0.0", "--port", "8081", "--reload"]
