from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import jobs

app = FastAPI(title="PolyMorph Web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
