import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.router import api_router
from app.core.config import get_settings
from app.core.clock import clock_from_settings
from app.core.errors import AppError
from app.services.agent.runtime import AgentRuntime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("personal_learning")
settings = get_settings()


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings_provider = application.dependency_overrides.get(get_settings, get_settings)
    runtime_settings = settings_provider()
    application.state.clock = clock_from_settings(runtime_settings)
    application.state.agent_runtime = AgentRuntime(runtime_settings)
    try:
        yield
    finally:
        application.state.agent_runtime.close()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    description="LearnPilot 本地优先个人学习与知识管理 API",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_prefix)


def error_body(code: str, message: str, details=None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.code, exc.message, exc.details),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic may place the original ValueError object in ``ctx``. Returning
    # that object directly makes an otherwise normal 422 fail JSON encoding.
    details = [{key: value for key, value in item.items() if key != "ctx"} for item in exc.errors()]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_body("validation_error", "输入参数校验失败", details),
    )


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("database_integrity_error path=%s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=error_body("database_conflict", "数据与现有记录冲突，请检查关联关系或顺序"),
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.exception("database_error path=%s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=error_body("database_error", "数据库暂时不可用，请稍后重试"),
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unexpected_error path=%s", request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=error_body("internal_error", "服务发生意外错误，请查看后端日志"),
    )
