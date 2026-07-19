from __future__ import annotations

from fastapi import FastAPI

from us_grad_recommender.api.routes import router as universities_router

app = FastAPI(
    title="US Graduate Recommender — Institution API",
    description="Read-only search/detail API over the institution index.",
    version="0.1.0",
)

app.include_router(universities_router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
