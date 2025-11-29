"""
FastAPI backend for MLOps Topic Tracker.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from contextlib import asynccontextmanager
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import get_config, get_logger, setup_logging, metrics

# Setup logging
setup_logging()
logger = get_logger(__name__)
config = get_config()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info(f"Starting {config.service_name} v1.0.0")
    logger.info(f"Environment: {config.environment}")
    yield
    # Shutdown
    logger.info("Shutting down application")


# Create FastAPI application
app = FastAPI(
    title="Pemerintah Topic Tracker API",
    description="MLOps API for Indonesian government topic modeling and analysis",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup Prometheus metrics
instrumentator = Instrumentator()
instrumentator.instrument(app).expose(app, endpoint="/metrics")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Pemerintah Topic Tracker API",
        "version": "1.0.0",
        "status": "operational"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": config.service_name,
        "environment": config.environment
    }


@app.get("/api/v1/status")
async def get_status():
    """Get system status with component health."""
    # TODO: Add actual component health checks
    return {
        "api": "healthy",
        "database": "healthy",  # Will implement actual check
        "storage": "healthy",   # Will implement actual check
        "cache": "healthy",     # Will implement actual check
        "mlflow": "healthy"     # Will implement actual check
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=config.api_host,
        port=config.api_port,
        reload=config.debug,
        log_level=config.log_level.lower()
    )
