from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from app.config import get_settings
from app.models import HealthResponse
from routes.activities import router as activities_router
from routes.chat import router as chat_router
from routes.faq import router as faq_router
from routes.logs import router as logs_router
from routes.orders import router as orders_router
from routes.quote import router as quote_router

logger = logging.getLogger(__name__)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "Day Experience AI API démarrée (debug=%s, cors=%s)",
        settings.debug,
        settings.cors_origin_list,
    )
    yield
    logger.info("Day Experience AI API arrêtée")


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="Day Experience AI",
        description="Agent IA conversationnel B2B pour partenaires Day Experience",
        version="0.3.0",
        lifespan=lifespan,
        debug=settings.debug,
    )

    if settings.debug:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        origins = settings.cors_origin_list or ["*"]
        application.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    application.include_router(activities_router)
    application.include_router(orders_router)
    application.include_router(quote_router)
    application.include_router(chat_router)
    application.include_router(faq_router)
    application.include_router(logs_router)

    @application.get("/", include_in_schema=False)
    async def frontend_root():
        index = FRONTEND_DIR / "index.html"
        if index.exists():
            return FileResponse(index)
        return RedirectResponse(url="/docs")

    @application.get("/logs", include_in_schema=False)
    async def frontend_logs():
        page = FRONTEND_DIR / "logs.html"
        if page.exists():
            return FileResponse(page)
        raise HTTPException(status_code=404, detail="logs page missing")

    @application.get("/styles.css", include_in_schema=False)
    async def frontend_css():
        return FileResponse(FRONTEND_DIR / "styles.css", media_type="text/css")

    @application.get("/app.js", include_in_schema=False)
    async def frontend_js():
        return FileResponse(FRONTEND_DIR / "app.js", media_type="application/javascript")

    @application.get("/logs.css", include_in_schema=False)
    async def frontend_logs_css():
        return FileResponse(FRONTEND_DIR / "logs.css", media_type="text/css")

    @application.get("/logs.js", include_in_schema=False)
    async def frontend_logs_js():
        return FileResponse(FRONTEND_DIR / "logs.js", media_type="application/javascript")

    @application.get("/health", response_model=HealthResponse, tags=["system"])
    async def health_check() -> HealthResponse:
        return HealthResponse()

    return application


app = create_app()
