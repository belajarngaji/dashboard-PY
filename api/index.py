from fastapi import FastAPI, HTTPException, Request, Response, Form
from fastapi.middleware.cors import CORSMiddleware
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from datetime import datetime
from typing import Optional, Dict
import os, uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert

# =========================
# FastAPI app & CORS
# =========================
app = FastAPI(title="Quiz Backend (Supabase)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # ganti ke domain kamu di production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Koneksi Database (Supabase)
# =========================
RAW_DB_URL = os.getenv("DATABASE_URL", "")
if not RAW_DB_URL:
    raise RuntimeError("ENV DATABASE_URL belum di-set di Vercel Settings → Environment Variables")

# Supabase memberi "postgresql://...". SQLAlchemy async butuh "postgresql+asyncpg://..."
DB_URL = RAW_DB_URL.replace("postgres://", "postgresql://")
if "+asyncpg" not in DB_URL:
    DB_URL = DB_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(DB_URL, echo=False, pool_pre_ping=True)
AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

metadata = sa.MetaData()

users = sa.Table(
    "users", metadata,
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("username", sa.Text, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
)

scores = sa.Table(
    "scores", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
    sa.Column("user_id", sa.Text, sa.ForeignKey("users.user_id", ondelete="CASCADE")),
    sa.Column("quiz_name", sa.Text, nullable=False),
    sa.Column("score", sa.Integer, nullable=False),
    sa.Column("timestamp", sa.DateTime(timezone=True), server_default=sa.text("now()")),
)

# =========================
# Soal kuis (contoh 1 soal)
# =========================
quiz_questions = {
    "Matematika Dasar": [
        {"question": "Berapakah hasil dari 15 + 20?", "answer": 35}
    ]
}

# =========================
# Session & auth (cookie)
# =========================
SECRET_KEY = os.getenv("SECRET_KEY", "ganti-ini-di-production")
serializer = URLSafeTimedSerializer(SECRET_KEY)
SESSION_COOKIE_NAME = "quiz_session"
SESSION_TIMEOUT = 60 * 60 * 24 * 7  # 7 hari

def create_session_token(user_id: str, username: str) -> str:
    return serializer.dumps({"user_id": user_id, "username": username})

def verify_session_token(token: str) -> Optional[Dict[str, str]]:
    try:
        return serializer.loads(token, max_age=SESSION_TIMEOUT)
    except (BadSignature, SignatureExpired):
        return None

def _deny():
    raise HTTPException(status_code=401, detail="Login diperlukan")

async def get_current_user(request: Request) -> Dict[str, str]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        _deny()
    data = verify_session_token(token)
    if not data:
        _deny()
    # pastikan user masih ada di DB
    async with AsyncSession() as session:
        r = await session.execute(sa.select(users.c.user_id).where(users.c.user_id == data["user_id"]))
        if not r.first():
            _deny()
    return data

# =========================
# Endpoints
# =========================
@app.post("/api/login")
async def login(response: Response, username: str = Form(...)):
    name = (username or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Nama pengguna tidak valid")

    async with AsyncSession() as session:
        # Cari user by username (case-insensitive)
        q = sa.select(users.c.user_id, users.c.username).where(sa.func.lower(users.c.username) == name.lower())
        res = await session.execute(q)
        row = res.first()

        if row:
            user_id = row.user_id
            message = f"Selamat datang kembali, {name}!"
        else:
            user_id = uuid.uuid4().hex
            await session.execute(users.insert().values(user_id=user_id, username=name))
            await session.commit()
            message = f"Akun baru dibuat untuk {name}!"

    token = create_session_token(user_id, name)
    response.set_cookie(
        key=SESSION_COOKIE_NAME, value=token,
        httponly=True, secure=True, samesite="lax", max_age=SESSION_TIMEOUT
    )
    return {"message": message, "username": name, "user_id": user_id}

@app.get("/api/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"message": "Berhasil logout"}

@app.post("/api/quiz/grade")
async def grade_quiz(request: Request, quiz_name: str = Form(...), answer: int = Form(...)):
    user = await get_current_user(request)
    uid = user["user_id"]

    if quiz_name not in quiz_questions:
        raise HTTPException(status_code=400, detail="Kuis tidak ditemukan")

    correct_answer = quiz_questions[quiz_name][0]["answer"]
    score = 100 if answer == correct_answer else 0

    async with AsyncSession() as session:
        # Cek apakah skor untuk kuis ini sudah ada → update, kalau belum → insert
        r = await session.execute(
            sa.select(scores.c.id).where(
                sa.and_(scores.c.user_id == uid, scores.c.quiz_name == quiz_name)
            )
        )
        row = r.first()
        if row:
            await session.execute(
                scores.update()
                .where(scores.c.id == row.id)
                .values(score=score, timestamp=sa.func.now())
            )
        else:
            await session.execute(
                scores.insert().values(user_id=uid, quiz_name=quiz_name, score=score)
            )
        await session.commit()

    return {"message": "Jawaban dinilai", "score": score}

@app.get("/api/profile")
async def profile(request: Request):
    user = await get_current_user(request)
    uid = user["user_id"]

    async with AsyncSession() as session:
        # nama user
        rname = await session.execute(sa.select(users.c.username).where(users.c.user_id == uid))
        uname = rname.scalar_one()

        # ambil skor
        r = await session.execute(
            sa.select(scores.c.quiz_name, scores.c.score, scores.c.timestamp)
            .where(scores.c.user_id == uid)
            .order_by(scores.c.timestamp.desc())
        )
        rows = r.fetchall()

    total = sum(row.score for row in rows) if rows else 0
    avg = round(total / len(rows), 2) if rows else 0

    return {
        "username": uname,
        "total_quizzes": len(rows),
        "total_score": total,
        "average_score": avg,
        "scores": [
            {"quiz_name": row.quiz_name, "score": row.score, "timestamp": row.timestamp.isoformat()}
            for row in rows
        ],
    }

@app.get("/api/leaderboard")
async def leaderboard():
    async with AsyncSession() as session:
        r = await session.execute(
            sa.select(
                users.c.username,
                sa.func.sum(scores.c.score).label("total_score"),
                sa.func.count(scores.c.id).label("quiz_count"),
                sa.func.avg(scores.c.score).label("average_score"),
            )
            .select_from(scores.join(users, scores.c.user_id == users.c.user_id))
            .group_by(users.c.user_id, users.c.username)
            .order_by(sa.text("total_score DESC"))
            .limit(10)
        )
        rows = r.fetchall()

    leaderboard = []
    for i, row in enumerate(rows, start=1):
        leaderboard.append({
            "rank": i,
            "username": row.username,
            "total_score": int(row.total_score) if row.total_score is not None else 0,
            "average_score": float(round(row.average_score or 0, 2)),
            "quiz_count": int(row.quiz_count or 0),
        })
    return {"leaderboard": leaderboard}

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("index:app", host="0.0.0.0", port=5000)
