# api/index.py
import os
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict
import time

from supabase import create_client, Client

from fastapi import FastAPI, Request, Response, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware

# -------------------------
# FastAPI app + CORS
# -------------------------
app = FastAPI(title="Quiz Backend (Supabase API)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# DATABASE
# -------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL atau SUPABASE_KEY belum di-set di environment")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

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
# ENDPOINTS
# -------------------------
@app.post("/api/signup")
async def signup(response: Response, username: str = Form(...), password: str = Form(...)):
    res = supabase.from_("users").select("*").eq("username", username).execute()
    user_exists = res.data
    
    if user_exists:
        time.sleep(0.5)
        raise HTTPException(status_code=400, detail="Username sudah terdaftar")
    
    hashed_password = hash_password(password)
    
    supabase.from_("users").insert({"username": username, "password": hashed_password, "role": "murid"}).execute()
    
    time.sleep(0.5)
    return {"message": "Akun baru berhasil dibuat"}

@app.post("/api/login")
async def login(response: Response, username: str = Form(...), password: str = Form(...)):
    res = supabase.from_("users").select("*").eq("username", username).execute()
    user = res.data
    
    if not user:
        time.sleep(0.5)
        raise HTTPException(status_code=400, detail="Nama pengguna atau kata sandi salah")
    
    user_data = user[0]
    is_correct_password = check_password(password, user_data.get("password"))
    
    if not is_correct_password:
        time.sleep(0.5)
        raise HTTPException(status_code=400, detail="Nama pengguna atau kata sandi salah")
        
    token = create_jwt_token({"username": user_data.get("username"), "role": user_data.get("role")})
    
    response.set_cookie(key="token", value=token, httponly=True, samesite="strict", secure=True, expires=datetime.utcnow() + timedelta(days=7))
    
    time.sleep(0.5)
    return {"message": "Selamat datang kembali", "username": user_data.get("username"), "role": user_data.get("role")}

@app.get("/api/profile")
async def get_profile(request: Request):
    token = request.cookies.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Tidak terautentikasi")
    
    payload = decode_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token tidak valid atau kedaluwarsa")
        
    username = payload.get("username")
    
    user_res = supabase.from_("users").select("*").eq("username", username).execute()
    user_profile = user_res.data
    
    if not user_profile:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")
    
    scores_res = supabase.from_("scores").select("*").eq("username", username).order("timestamp", desc=True).execute()
    user_scores = scores_res.data
    
    return {
        "profile": {
            "username": user_profile[0].get("username"),
            "role": user_profile[0].get("role"),
        },
        "scores": user_scores
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
    
    supabase.from_("scores").insert({"username": username, "quiz_name": quiz_name, "score": score}).execute()
    
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
        
    res = supabase.from_("users").select("username, role").eq("role", "murid").order("username").execute()
    rows = res.data

    return {
        "murid": rows
    }

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
        
    res = supabase.from_("scores").select("*").eq("username", username).order("timestamp", desc=True).execute()
    rows = res.data

    return {
        "scores": rows
    }

@app.get("/api/leaderboard")
async def leaderboard():
    res = supabase.rpc("get_leaderboard").execute()
    rows = res.data

    return {
        "leaderboard": rows
    }

@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

