
import boto3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.routers import video, auth, photo_validation, video_jobs, admin_auth
from app.core.redis import RedisClient
from app.core.config import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup and shutdown events"""
    print("\n" + "=" * 50)
    print("  Starting Closeup API...")
    print("=" * 50)
    print(f"  Environment: {settings.APP_ENV}")
    print("-" * 50)

    try:
        from sqlalchemy import text
        from app.core.database import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("  [OK]   MySQL")
    except Exception as e:
        print(f"  [FAIL] MySQL     - {e}")

    try:
        RedisClient.get_client()
        RedisClient._client.ping()
        print(f"  [OK]   Redis     ({settings.REDIS_HOST}:{settings.REDIS_PORT})")
    except Exception as e:
        print(f"  [FAIL] Redis     - {e}")

    try:
        import botocore
        from app.core.s3 import s3_client
        sts = boto3.client(
            "sts",
            region_name=settings.AWS_REGION,
            **({"aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY}
               if settings.AWS_ACCESS_KEY_ID else {}),
        )
        identity = sts.get_caller_identity()
        mode = "IAM Role" if ":assumed-role/" in identity["Arn"] else "Access Key"
        print(f"  [OK]   S3        ({settings.AWS_S3_BUCKET} via {mode})")
    except Exception as e:
        print(f"  [FAIL] S3        - {e}")

    try:
        import httpx
        resp = httpx.get(
            settings.WHATSAPP_API_URL,
            headers={"X-API-KEY": settings.WHATSAPP_API_KEY},
            timeout=5.0,
        )
        print(f"  [OK]   WhatsApp  (status {resp.status_code})")
    except Exception as e:
        print(f"  [FAIL] WhatsApp  - {e}")

    print("-" * 50)
    print("  Closeup API is ready!")
    print("=" * 50 + "\n")
    yield

    print("\nShutting down Closeup API...")
    try:
        RedisClient.close()
    except Exception:
        pass


is_production = settings.APP_ENV == "production"

app = FastAPI(
    title="Closeup API",
    lifespan=lifespan,
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://admin.closeuplovetunes.in",
        "https://closeuplovetunes.in",
        "https://www.closeuplovetunes.in",
        "https://rock.closeuplovetunes.in",
        "https://test.closeuplovetunes.in"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def health_check():
    return {"status": True}


app.include_router(video.router)
app.include_router(auth.router)
app.include_router(photo_validation.router)
app.include_router(video_jobs.router)
app.include_router(admin_auth.router)







# import boto3
# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from contextlib import asynccontextmanager
# from app.routers import video, auth, photo_validation, video_jobs, admin_auth
# from app.core.redis import RedisClient
# from app.core.config import settings


# @asynccontextmanager
# async def lifespan(_app: FastAPI):
#     """Startup and shutdown events"""
#     print("\n" + "=" * 50)
#     print("  Starting Closeup API...")
#     print("=" * 50)
#     print(f"  Environment: {settings.APP_ENV}")
#     print("-" * 50)

#     # Check MySQL
#     try:
#         from sqlalchemy import text
#         from app.core.database import engine
#         with engine.connect() as conn:
#             conn.execute(text("SELECT 1"))
#         print("  [OK]   MySQL")
#     except Exception as e:
#         print(f"  [FAIL] MySQL     - {e}")

#     # Check Redis
#     try:
#         RedisClient.get_client()
#         RedisClient._client.ping()
#         print(f"  [OK]   Redis     ({settings.REDIS_HOST}:{settings.REDIS_PORT})")
#     except Exception as e:
#         print(f"  [FAIL] Redis     - {e}")

#     # Check S3
#     try:
#         import botocore
#         from app.core.s3 import s3_client
#         sts = boto3.client(
#             "sts",
#             region_name=settings.AWS_REGION,
#             **({"aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
#                 "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY}
#                if settings.AWS_ACCESS_KEY_ID else {}),
#         )
#         identity = sts.get_caller_identity()
#         mode = "IAM Role" if ":assumed-role/" in identity["Arn"] else "Access Key"
#         print(f"  [OK]   S3        ({settings.AWS_S3_BUCKET} via {mode})")
#     except Exception as e:
#         print(f"  [FAIL] S3        - {e}")

#     # Check WhatsApp API
#     try:
#         import httpx
#         resp = httpx.get(
#             settings.WHATSAPP_API_URL,
#             headers={"X-API-KEY": settings.WHATSAPP_API_KEY},
#             timeout=5.0,
#         )
#         print(f"  [OK]   WhatsApp  (status {resp.status_code})")
#     except Exception as e:
#         print(f"  [FAIL] WhatsApp  - {e}")

#     print("-" * 50)
#     print("  Closeup API is ready!")
#     print("=" * 50 + "\n")

#     yield

#     # Shutdown
#     print("\nShutting down Closeup API...")
#     try:
#         RedisClient.close()
#     except Exception:
#         pass


# is_production = settings.APP_ENV == "production"

# app = FastAPI(
#     title="Closeup API",
#     lifespan=lifespan,
#     docs_url=None if is_production else "/docs",
#     redoc_url=None if is_production else "/redoc",
# )

# # Configure CORS
# # app.add_middleware(
# #     CORSMiddleware,
# #     allow_origins=[
# #         "http://localhost:3000",
# #         "http://localhost:3001",
# #         "http://localhost:8110",
# #         "http://127.0.0.1:3000",
# #         "http://127.0.0.1:8110",
# #         "http://192.168.1.43:3001",  # Local network access
# #     ],
# #     allow_credentials=True,
# #     allow_methods=["*"],  # Allows all methods (GET, POST, PUT, DELETE, etc.)
# #     allow_headers=["*"],  # Allows all headers
# # )

# app.include_router(video.router)
# app.include_router(auth.router)
# app.include_router(photo_validation.router)
# app.include_router(video_jobs.router)
# app.include_router(admin_auth.router)
