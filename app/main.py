from fastapi import FastAPI

from app import models
from app.config import settings
from app.db import Base, engine
from app.routers.analyses import router as analyses_router
from app.routers.datasets import router as datasets_router
from app.routers.reports import router as reports_router


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
)

Base.metadata.create_all(bind=engine)

app.include_router(analyses_router)
app.include_router(datasets_router)
app.include_router(reports_router)


@app.get("/health")
def health():
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("SELECT 1")

        return {
            "status": "ok",
            "database": "ok",
        }

    except Exception:
        return {
            "status": "degraded",
            "database": "unavailable",
        }