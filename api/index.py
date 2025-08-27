from fastapi import FastAPI, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from itsdangerous import URLSafeSerializer
import os
from datetime import datetime

app = FastAPI()

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not found in environment")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Token serializer
serializer = URLSafeSerializer("supersecretkey")

# Dependency
async def get_db():
    async with async_session() as session:
        yield session

# Login endpoint (guru/murid)
@app.post("/api/login")
async def login(username: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    q = text("SELECT role FROM users WHERE username = :u AND password = :p")
    res = await db.execute(q, {"u": username, "p": password})
    row = res.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Username atau password salah")
    role = row[0]
    token = serializer.dumps({"username": username, "role": role})
    return {"message": "Login berhasil", "token": token, "role": role}

# Submit jawaban quiz
@app.post("/api/quiz/grade")
async def grade_quiz(username: str = Form(...), quiz_name: str = Form(...), answer: int = Form(...), db: AsyncSession = Depends(get_db)):
    # Penilaian otomatis contoh sederhana
    correct_answer = 42
    score = 100 if answer == correct_answer else 0

    # Simpan skor
    await db.execute(
        text("""INSERT INTO scores (username, quiz_name, score, timestamp)
                VALUES (:u, :q, :s, :t)"""),
        {"u": username, "q": quiz_name, "s": score, "t": datetime.utcnow()},
    )
    await db.commit()
    return {"message": "Skor berhasil disimpan", "score": score}

# Profil murid
@app.get("/api/profile")
async def profile(username: str, db: AsyncSession = Depends(get_db)):
    q1 = text("SELECT COUNT(*), COALESCE(SUM(score), 0), COALESCE(AVG(score), 0) FROM scores WHERE username = :u")
    res1 = await db.execute(q1, {"u": username})
    total_quizzes, total_score, average_score = res1.fetchone()

    q2 = text("SELECT quiz_name, score, timestamp FROM scores WHERE username = :u ORDER BY timestamp DESC")
    res2 = await db.execute(q2, {"u": username})
    scores = [{"quiz_name": r[0], "score": r[1], "timestamp": r[2].isoformat()} for r in res2.fetchall()]

    return {
        "username": username,
        "total_quizzes": total_quizzes,
        "total_score": total_score,
        "average_score": round(average_score, 2),
        "scores": scores,
    }

# Leaderboard
@app.get("/api/leaderboard")
async def leaderboard(db: AsyncSession = Depends(get_db)):
    q = text("""
        SELECT username,
               SUM(score) AS total_score,
               AVG(score) AS average_score
        FROM scores
        GROUP BY username
        ORDER BY total_score DESC
        LIMIT 10
    """)
    res = await db.execute(q)
    data = []
    rank = 1
    for row in res.fetchall():
        data.append({
            "rank": rank,
            "username": row[0],
            "total_score": row[1],
            "average_score": round(row[2], 2)
        })
        rank += 1
    return {"leaderboard": data}
