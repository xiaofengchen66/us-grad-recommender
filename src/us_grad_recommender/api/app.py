from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from us_grad_recommender.api.routes import router as universities_router

app = FastAPI(
    title="US Graduate Recommender — Institution API",
    description="Read-only search/detail API over the institution index.",
    version="0.1.0",
)

# Local frontend dev servers only (Next.js default ports). This is a
# read-only, unauthenticated API with no cookies/session state, so origin
# restriction here is about keeping the allowlist intentional as real
# deployments are added later, not about protecting sensitive data.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(universities_router)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}
