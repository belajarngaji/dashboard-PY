# api/index.py
import os
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict

import sqlalchemy as sa
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from fastapi import FastAPI, Request, Response, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# -------------------------
# FastAPI app + CORS
# -------------------------
app = FastAPI(title="Quiz Backend (Supabase)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # production: ganti ke domain frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# DATABASE
# -------------------------
RAW_DB_URL = os.getenv("SUPABASE_URL", "")
if not RAW_DB_URL:
    raise RuntimeError("SUPABASE_URL belum di-set di environment")

DB_URL = RAW_DB_URL
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DB_URL.startswith("postgresql://") and "+asyncpg" not in DB_URL:
    DB_URL = DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(
    DB_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0}
)
AsyncSessionMaker = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

# -------------------------
# MODEL
# -------------------------
meta = sa.MetaData()
users = sa.Table(
    "users",
    meta,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("username", sa.String(255), unique=True, nullable=False),
    sa.Column("password", sa.String(255), nullable=False),
    sa.Column("role", sa.String(50), nullable=False),
)
scores = sa.Table(
    "scores",
    meta,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("username", sa.String(255), nullable=False),
    sa.Column("quiz_name", sa.String(255), nullable=False),
    sa.Column("score", sa.Integer, nullable=False),
    sa.Column("timestamp", sa.DateTime, server_default=sa.func.now(), nullable=False),
)

# -------------------------
# AUTHENTICATION & SECURITY
# -------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "super-secret-key-jangan-dipakai-di-prod")

def hash_password(password: str):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password: str, hashed_password: str):
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_jwt_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=7)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
    return encoded_jwt

def decode_jwt_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

# -------------------------
# GLOBAL EXCEPTION HANDLER
# -------------------------
@app.exception_handler(Exception)
async def all_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error"}
    )

# -------------------------
# ENDPOINTS
# -------------------------
@app.post("/api/signup")
async def signup(username: str = Form(...), password: str = Form(...)):
    async with AsyncSessionMaker() as session:
        q_user = sa.select(users).where(users.c.username == username)
        res = await session.execute(q_user)
        user_exists = res.scalar_one_or_none()

        if user_exists:
            await asyncio.sleep(0.5)
            raise HTTPException(status_code=400, detail="Username sudah terdaftar")

        hashed_password = hash_password(password)
        q_insert = sa.insert(users).values(
            username=username, password=hashed_password, role="murid"
        ).returning(users)

        await session.execute(q_insert)
        await session.commit()

    await asyncio.sleep(0.5)
    return {"message": "Akun baru berhasil dibuat"}

@app.post("/api/login")
async def login(response: Response, username: str = Form(...), password: str = Form(...)):
    async with AsyncSessionMaker() as session:
        q = sa.select(users).where(users.c.username == username)
        res = await session.execute(q)
        user = res.scalar_one_or_none()

    if not user:
        await asyncio.sleep(0.5)
        raise HTTPException(status_code=400, detail="Nama pengguna atau kata sandi salah")

    if not check_password(password, user.password):
        await asyncio.sleep(0.5)
        raise HTTPException(status_code=400, detail="Nama pengguna atau kata sandi salah")

    token = create_jwt_token({"username": user.username, "role": user.role})
    response.set_cookie(
        key="token",
        value=token,
        httponly=True,
        samesite="strict",
        secure=True,
        expires=datetime.utcnow() + timedelta(days=7)
    )

    await asyncio.sleep(0.5)
    return {"message": "Selamat datang kembali", "username": user.username, "role": user.role}

@app.get("/api/profile")
async def get_profile(request: Request):
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi")

    payload = decode_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token tidak valid atau kedaluwarsa")

    username = payload.get("username")
    async with AsyncSessionMaker() as session:
        q_user = sa.select(users).where(users.c.username == username)
        res_user = await session.execute(q_user)
        user_profile = res_user.scalar_one_or_none()

        if not user_profile:
            raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

        q_scores = sa.select(scores).where(scores.c.username == username).order_by(scores.c.timestamp.desc())
        res_scores = await session.execute(q_scores)
        user_scores = res_scores.fetchall()

    return {
        "profile": {"username": user_profile.username, "role": user_profile.role},
        "scores": [
            {"quiz_name": row.quiz_name, "score": row.score,
             "timestamp": row.timestamp.isoformat() if row.timestamp else None}
            for row in user_scores
        ]
    }

@app.post("/api/submit_quiz")
async def submit_quiz(request: Request, quiz_name: str = Form(...), score: int = Form(...)):
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi")

    payload = decode_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token tidak valid atau kedaluwarsa")

    username = payload.get("username")
    async with AsyncSessionMaker() as session:
        q_insert = sa.insert(scores).values(
            username=username, quiz_name=quiz_name, score=score
        ).returning(scores)
        await session.execute(q_insert)
        await session.commit()

    return {"message": "Skor kuis berhasil disimpan"}

@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie(key="token")
    return {"message": "Berhasil logout"}

@app.get("/api/murid")
async def get_murid(request: Request):
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi")

    payload = decode_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token tidak valid atau kedaluwarsa")

    if payload.get("role") != "guru":
        raise HTTPException(status_code=403, detail="Akses ditolak")

    async with AsyncSessionMaker() as session:
        q = sa.select(users).where(users.c.role == "murid").order_by(users.c.username)
        res = await session.execute(q)
        rows = res.fetchall()

    return {"murid": [{"username": row.username, "role": row.role} for row in rows]}

@app.get("/api/murid_scores")
async def murid_scores(request: Request, username: str):
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi")

    payload = decode_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token tidak valid atau kedaluwarsa")

    if payload.get("role") != "guru":
        raise HTTPException(status_code=403, detail="Akses ditolak")

    async with AsyncSessionMaker() as session:
        q = sa.select(scores).where(scores.c.username == username).order_by(scores.c.timestamp.desc())
        res = await session.execute(q)
        rows = res.fetchall()

    return {"scores": [{"quiz_name": row.quiz_name, "score": row.score,
                        "timestamp": row.timestamp.isoformat() if row.timestamp else None} for row in rows]}

@app.get("/api/leaderboard")
async def leaderboard():
    async with AsyncSessionMaker() as session:
        r = await session.execute(
            sa.select(
                scores.c.username,
                sa.func.sum(scores.c.score).label("total_score"),
                sa.func.avg(scores.c.score).label("average_score"),
                sa.func.count(scores.c.id).label("quiz_count")
            )
            .group_by(scores.c.username)
            .order_by(sa.text("total_score DESC"))
            .limit(10)
        )
        rows = r.fetchall()

    return {
        "leaderboard": [
            {
                "rank": i + 1,
                "username": row.username,
                "total_score": int(row.total_score or 0),
                "average_score": float(round(row.average_score or 0, 2)),
                "quiz_count": int(row.quiz_count or 0),
            }
            for i, row in enumerate(rows)
        ]
    }

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

# -------------------------
# Shutdown event untuk dispose engine
# -------------------------
@app.on_event("shutdown")
async def shutdown_event():
    print("Shutting down the application...")
    await asyncio.sleep(0.250)
    await engine.dispose()
    print("Database connections closed.")