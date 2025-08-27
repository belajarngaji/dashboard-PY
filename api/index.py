# api/index.py
import os
import bcrypt
from datetime import datetime
from typing import Optional, Dict

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from fastapi import FastAPI, Request, Response, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

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
RAW_DB_URL = os.getenv("DATABASE_URL", "")
if not RAW_DB_URL:
    raise RuntimeError("DATABASE_URL belum di-set di environment")

DB_URL = RAW_DB_URL
if DB_URL.startswith("postgres://"):
    DB_URL = DB_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DB_URL.startswith("postgresql://") and "+asyncpg" not in DB_URL:
    DB_URL = DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# engine global, statement_cache_size=0 untuk pgbouncer transaction mode
engine = create_async_engine(
    DB_URL,
    echo=False,
    pool_pre_ping=True,
    connect_args={"statement_cache_size": 0}
)
AsyncSessionMaker = async_sessionmaker(engine, expire_on_commit=False)
metadata = sa.MetaData()

# -------------------------
# Tables
# -------------------------
users = sa.Table(
    "users", metadata,
    sa.Column("username", sa.Text, primary_key=True),
    sa.Column("password", sa.Text, nullable=False),
    sa.Column("role", sa.Text, nullable=False),
)

scores = sa.Table(
    "scores", metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("username", sa.Text, sa.ForeignKey("users.username", ondelete="CASCADE")),
    sa.Column("quiz_name", sa.Text),
    sa.Column("score", sa.Integer),
    sa.Column("timestamp", sa.DateTime(timezone=False)),
)

# -------------------------
# Quiz bank
# -------------------------
quiz_questions = {
    "Matematika Dasar": [
        {"question": "Berapakah hasil dari 15 + 20?", "answer": 35}
    ]
}

# -------------------------
# Session tokens
# -------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "ganti-ini-di-production")
serializer = URLSafeTimedSerializer(SECRET_KEY)
SESSION_COOKIE_NAME = "quiz_session"
SESSION_TIMEOUT = 60 * 60 * 24 * 7  # 7 hari

def create_session_token(username: str, role: str) -> str:
    return serializer.dumps({"username": username, "role": role})

def verify_session_token(token: str) -> Optional[Dict[str, str]]:
    try:
        return serializer.loads(token, max_age=SESSION_TIMEOUT)
    except (BadSignature, SignatureExpired):
        return None

async def get_current_user(request: Request) -> Dict[str, str]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Login diperlukan")
    data = verify_session_token(token)
    if not data:
        raise HTTPException(status_code=401, detail="Token tidak valid atau kadaluarsa")

    async with AsyncSessionMaker() as session:
        q = sa.select(users.c.username, users.c.role).where(users.c.username == data["username"])
        res = await session.execute(q)
        row = res.first()
        if not row:
            raise HTTPException(status_code=401, detail="User tidak ditemukan")

    return {"username": data["username"], "role": data.get("role", "")}

# -------------------------
# API Endpoints
# -------------------------
@app.post("/api/login")
async def login(response: Response, username: str = Form(...), password: str = Form(...)):
    username = username.strip().lower()
    if len(username) < 2:
        raise HTTPException(status_code=400, detail="Nama pengguna tidak valid")

    async with AsyncSessionMaker() as session:
        q = sa.select(users.c.username, users.c.password, users.c.role).where(users.c.username == username)
        res = await session.execute(q)
        row = res.first()

        if not row:
            raise HTTPException(status_code=401, detail="Username atau password salah")
        
        db_username, db_password, db_role = row
        if not bcrypt.checkpw(password.encode('utf-8'), db_password.encode('utf-8')):
            raise HTTPException(status_code=401, detail="Username atau password salah")
        
        token = create_session_token(db_username, db_role)
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=token,
            httponly=True,
            samesite="lax",
            max_age=SESSION_TIMEOUT
        )
        return {"message": f"Selamat datang kembali, {db_username}!", "username": db_username, "role": db_role}

@app.post("/api/signup")
async def signup(response: Response, username: str = Form(...), password: str = Form(...)):
    username = username.strip().lower()
    if len(username) < 2:
        raise HTTPException(status_code=400, detail="Nama pengguna tidak valid")

    async with AsyncSessionMaker() as session:
        # Cek apakah username sudah ada
        q = sa.select(users.c.username).where(users.c.username == username)
        res = await session.execute(q)
        if res.first():
            raise HTTPException(status_code=409, detail="Username sudah digunakan")

        # Hash password dan buat akun baru
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        role = "murid"
        
        await session.execute(users.insert().values(username=username, password=hashed_password, role=role))
        await session.commit()
    
    token = create_session_token(username, role)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=SESSION_TIMEOUT
    )
    return {"message": f"Akun baru dibuat untuk {username}!", "username": username, "role": role}

@app.get("/api/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"message": "Berhasil logout"}

@app.post("/api/quiz/grade")
async def grade_quiz(request: Request, quiz_name: str = Form(...), answer: int = Form(...)):
    user = await get_current_user(request)
    username = user["username"]

    if quiz_name not in quiz_questions:
        raise HTTPException(status_code=400, detail="Kuis tidak ditemukan")

    correct_answer = quiz_questions[quiz_name][0]["answer"]
    score = 100 if answer == correct_answer else 0

    async with AsyncSessionMaker() as session:
        await session.execute(
            scores.insert().values(username=username, quiz_name=quiz_name, score=score, timestamp=datetime.utcnow())
        )
        await session.commit()

    return {"message": "Jawaban dinilai", "score": score}

@app.get("/api/profile")
async def profile(request: Request):
    user = await get_current_user(request)
    username = user["username"]

    async with AsyncSessionMaker() as session:
        r = await session.execute(
            sa.select(scores.c.quiz_name, scores.c.score, scores.c.timestamp)
            .where(scores.c.username == username)
            .order_by(scores.c.timestamp.desc())
        )
        rows = r.fetchall()

    total = sum(r.score for r in rows) if rows else 0
    avg = round(total / len(rows), 2) if rows else 0.0

    return {
        "username": username,
        "total_quizzes": len(rows),
        "total_score": total,
        "average_score": avg,
        "scores": [
            {"quiz_name": row.quiz_name, "score": row.score, "timestamp": (row.timestamp.isoformat() if row.timestamp else None)}
            for row in rows
        ],
    }

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
    await engine.dispose()
                                
