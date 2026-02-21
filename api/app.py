# -*- coding: utf-8 -*-
"""
===================================
FastAPI 应用工厂模块 - 增强版
===================================

职责：
1. 创建和配置 FastAPI 应用实例
2. 配置 CORS 中间件
3. 注册路由和异常处理器
4. 托管前端静态文件（生产模式）
5. 新增双源分析投喂口
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

# 核心修改：增加了 Form, File, UploadFile 以支持文件上传
from fastapi import FastAPI, Request, Form, File, UploadFile 
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.v1 import api_v1_router
from api.middlewares.auth import add_auth_middleware
from api.middlewares.error_handler import add_error_handlers
from api.v1.schemas.common import RootResponse, HealthResponse
from src.services.system_config_service import SystemConfigService

# 核心修改：导入你的分析服务层
from analyzer_service import analyze_stock

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    """Initialize and release shared services for the app lifecycle."""
    app.state.system_config_service = SystemConfigService()
    try:
        yield
    finally:
        if hasattr(app.state, "system_config_service"):
            delattr(app.state, "system_config_service")


def create_app(static_dir: Optional[Path] = None) -> FastAPI:
    """
    创建并配置 FastAPI 应用实例
    """
    # 默认静态文件目录
    if static_dir is None:
        static_dir = Path(__file__).parent.parent / "static"
    
    # 创建 FastAPI 实例
    app = FastAPI(
        title="Daily Stock Analysis API",
        description=(
            "A股/港股/美股自选股智能分析系统 API\n\n"
            "## 功能模块\n"
            "- 股票分析：触发 AI 智能分析\n"
            "- 双源投喂：结合研报文件进行分析\n"
            "- 历史记录：查询历史分析报告\n"
        ),
        version="1.1.0",
        lifespan=app_lifespan,
    )
    
    # ============================================================
    # CORS 配置
    # ============================================================
    allowed_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    
    extra_origins = os.environ.get("CORS_ORIGINS", "")
    if extra_origins:
        allowed_origins.extend([o.strip() for o in extra_origins.split(",") if o.strip()])
    
    if os.environ.get("CORS_ALLOW_ALL", "").lower() == "true":
        allowed_origins = ["*"]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    add_auth_middleware(app)
    
    # ============================================================
    # 注册原有路由
    # ============================================================
    app.include_router(api_v1_router)
    add_error_handlers(app)

    # ============================================================
    # 新增：双源分析“投喂口”接口
    # ============================================================
    @app.post("/api/v1/stock/analyze-with-file", tags=["Stock Analysis"])
    async def analyze_with_file(
        stock_code: str = Form(...),
        full_report: bool = Form(False),
        file: UploadFile = File(...)
    ):
        """
        双源分析：接收用户投喂的文件，结合数据库与联网数据进行标注分析
        """
        # 读取上传的文件内容
        file_name = file.filename
        content_bytes = await file.read()
        
        # 尝试解码内容
        try:
            file_text = content_bytes.decode("utf-8")
        except Exception:
            file_text = "内容解析失败，请确保投喂的是纯文本格式（.txt / .csv）。"

        # 调用我们在 analyzer_service.py 中增强的分析逻辑
        result = analyze_stock(
            stock_code=stock_code,
            full_report=full_report,
            reliable_file_content=file_text,
            reliable_file_name=file_name
        )

        return {
            "status": "success",
            "stock_code": stock_code,
            "filename": file_name,
            "analysis": result.content if result else "AI 分析引擎未返回结果"
        }
    
    # ============================================================
    # 根路由和健康检查
    # ============================================================
    has_frontend = static_dir.exists() and (static_dir / "index.html").exists()
    
    if has_frontend:
        @app.get("/", include_in_schema=False)
        async def root():
            return FileResponse(static_dir / "index.html")
    else:
        @app.get("/", response_model=RootResponse, tags=["Health"])
        async def root() -> RootResponse:
            return RootResponse(
                message="Daily Stock Analysis API is running",
                version="1.1.0"
            )
    
    @app.get("/api/health", response_model=HealthResponse, tags=["Health"])
    async def health_check() -> HealthResponse:
        return HealthResponse(
            status="ok",
            timestamp=datetime.now().isoformat()
        )
    
    # ============================================================
    # 静态文件托管
    # ============================================================
    if has_frontend:
        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
        
        @app.get("/{full_path:path}", include_in_schema=False)
        async def serve_spa(request: Request, full_path: str):
            if full_path.startswith("api/"):
                return None
            
            file_path = static_dir / full_path
            if file_path.exists() and file_path.is_file():
                return FileResponse(file_path)
            
            return FileResponse(static_dir / "index.html")
    
    return app

# 默认应用实例
app = create_app()
