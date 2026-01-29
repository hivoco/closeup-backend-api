from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routers import video, auth, photo_validation, video_jobs, admin_auth
from app.core.redis import RedisClient


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup and shutdown events"""
    # Startup
    print("🚀 Starting Closeup API...")

    # Try to connect to Redis
    try:
        RedisClient.get_client()
        print("✅ Redis connected successfully!")
        print(f"📍 Redis Host: {RedisClient._client.connection_pool.connection_kwargs.get('host')}")
    except Exception as e:
        print(f"⚠️ Redis connection failed: {str(e)}")
        print("⚠️ Application will continue without Redis caching")
        print("💡 Note: Redis requires VPC access when using AWS ElastiCache")

    yield

    # Shutdown
    print("🛑 Shutting down Closeup API...")
    try:
        RedisClient.close()
    except Exception:
        pass


app = FastAPI(title="Closeup API", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:8110",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8110",
        "http://192.168.1.43:3001",  # Local network access
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"],  # Allows all headers
)

app.include_router(video.router)
app.include_router(auth.router)
app.include_router(photo_validation.router)
app.include_router(video_jobs.router)
app.include_router(admin_auth.router)
