from fastapi import FastAPI

from app.routes import health, ingest

app = FastAPI(title="Leer API", version="0.1.0")

app.include_router(health.router)
app.include_router(ingest.router)
