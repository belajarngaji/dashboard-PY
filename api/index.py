from fastapi import FastAPI, HTTPException, Request, Response, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, Dict
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from datetime import datetime, timedelta
import uvicorn
import os

app = FastAPI(
    title="Quiz Backend API - Professional Edition",
    description="Backend profesional untuk aplikasi web kuis dengan login tanpa kata sandi dan pemantauan data"
)

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # ganti di produksi dengan domain frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database sementara (in-memory)
users_db = {}
scores_db = {}

# Konfigurasi sesi
SECRET_KEY = os.getenv("SECRET_KEY", "quiz-secret-key-change-in-production")
serializer = URLSafeTimedSerializer(SECRET_KEY)
SESSION_COOKIE_NAME = "quiz_session"
SESSION_TIMEOUT = 3600 * 24 * 7  # 7 hari

# Reset otomatis
last_reset_time = datetime.now()
RESET_INTERVAL_DAYS = 7

def check_and_reset_data():
    global last_reset_time, users_db, scores_db
    now = datetime.now()
    if now - last_reset_time >= timedelta(days=RESET_INTERVAL_DAYS):
        users_db.clear()
        scores_db.clear()
        last_reset_time = now
        return True
    return False

def create_session_token(user_id: str, username: str) -> str:
    return serializer.dumps({"user_id": user_id, "username": username})

def verify_session_token(token: str) -> Optional[Dict[str, str]]:
    try:
        return serializer.loads(token, max_age=SESSION_TIMEOUT)
    except (BadSignature, SignatureExpired):
        return None

def get_current_user(request: Request) -> Optional[Dict[str, str]]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    data = verify_session_token(token)
    if not data or data["user_id"] not in users_db:
        return None
    return data

def require_auth(request: Request) -> Dict[str, str]:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Login diperlukan")
    return user

# =======================
#   API ENDPOINTS
# =======================

@app.post("/api/login")
async def login(response: Response, username: str = Form(...)):
    check_and_reset_data()
    if not username or len(username.strip()) < 2:
        raise HTTPException(status_code=400, detail="Nama pengguna tidak valid")

    username = username.strip()
    existing_user_id = next((uid for uid, u in users_db.items() if u["username"].lower() == username.lower()), None)

    if existing_user_id:
        user_id = existing_user_id
        message = f"Selamat datang kembali, {username}!"
    else:
        user_id = f"user_{len(users_db)+1}_{username}"
        users_db[user_id] = {"username": username, "created_at": datetime.now()}
        scores_db[user_id] = {}
        message = f"Akun baru dibuat untuk {username}!"

    token = create_session_token(user_id, username)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,  # aktifkan HTTPS
        samesite="lax",
        max_age=SESSION_TIMEOUT
    )
    return {"message": message, "username": username, "user_id": user_id}

@app.get("/api/logout")
async def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)
    return {"message": "Berhasil logout"}

@app.post("/api/quiz/submit")
async def submit_quiz(request: Request, quiz_name: str = Form(...), score: int = Form(...)):
    check_and_reset_data()
    user = require_auth(request)
    uid = user["user_id"]

    if not quiz_name.strip():
        raise HTTPException(status_code=400, detail="Nama kuis diperlukan")
    if score < 0:
        raise HTTPException(status_code=400, detail="Skor tidak boleh negatif")

    scores_db.setdefault(uid, {})[quiz_name] = {"score": score, "timestamp": datetime.now()}
    return {"message": "Skor disimpan", "quiz_name": quiz_name, "score": score}

@app.get("/api/profile")
async def profile(request: Request):
    user = require_auth(request)
    uid = user["user_id"]
    user_scores = scores_db.get(uid, {})

    formatted = [
        {"quiz_name": q, "score": d["score"], "timestamp": d["timestamp"].isoformat()}
        for q, d in user_scores.items()
    ]
    formatted.sort(key=lambda x: x["timestamp"], reverse=True)

    total = sum(d["score"] for d in user_scores.values())
    return {
        "username": user["username"],
        "total_quizzes": len(formatted),
        "total_score": total,
        "average_score": round(total / len(formatted), 2) if formatted else 0,
        "scores": formatted
    }

@app.get("/api/leaderboard")
async def leaderboard():
    check_and_reset_data()
    data = []
    for uid, quizzes in scores_db.items():
        if uid in users_db and quizzes:
            total = sum(q["score"] for q in quizzes.values())
            count = len(quizzes)
            data.append({
                "username": users_db[uid]["username"],
                "total_score": total,
                "quiz_count": count,
                "average_score": round(total / count, 2)
            })
    data.sort(key=lambda x: x["total_score"], reverse=True)
    for i, entry in enumerate(data[:10]):
        entry["rank"] = i+1
    return {"leaderboard": data[:10]}

@app.get("/health")
async def health():
    return {"status": "healthy", "time": datetime.now().isoformat()}

# =======================
#   MAIN ENTRY (opsional)
# =======================
if __name__ == "__main__":
    uvicorn.run("index:app", host="0.0.0.0", port=5000)
