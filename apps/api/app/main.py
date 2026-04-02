from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import artifacts, health, ingest, runs

app = FastAPI(title="Leer API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(runs.router)
app.include_router(artifacts.router)
