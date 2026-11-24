"""Small web API so any front end (Lovable, React, Streamlit) can use the engine.

Start (in the hypoclimate folder):  uvicorn backend.api:app --reload
Try:    http://127.0.0.1:8000/score?address=Gerberngasse%2020,%203011%20Bern&value=1250000&mortgage=800000&mode=example
Docs:   http://127.0.0.1:8000/docs
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from . import engine

app = FastAPI(title="HypoClimate API", version="1")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"],
                   allow_headers=["*"])


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/score")
def score(address: str, value: float | None = None, mortgage: float | None = None,
          mode: str = "live"):
    if mode not in ("live", "example"):
        raise HTTPException(400, "mode must be 'live' or 'example'")
    try:
        return engine.score(address, value, mortgage, mode=mode)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
