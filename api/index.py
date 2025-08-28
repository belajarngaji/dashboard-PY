api/index.py
import os
import time
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional, Dict

from supabase import create_client, Client
from fastapi import FastAPI, Request, Response, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware

#-------------------------
FastAPI app + CORS
#-------------------------

app = FastAPI(title="Quiz Backend (Supabase API)")

app.add_middleware( CORSMiddleware, allow_origins=[""], allow_credentials=True, allow_methods=[""], allow_headers=["*"], )

#-------------------------
#DATABASE
#-------------------------


#-------------------------
#AUTHENTICATION & SECURITY
#-------------------------



def hash_password(password: str): return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def check_password(password: str, hashed_password: str): return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

def create_jwt_token(data: dict): to_encode = data.copy() expire = datetime.utcnow() + timedelta(days=7) to_encode.update({"exp": expire}) encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm="HS256") return encoded_jwt

def decode_jwt_token(token: str): try: payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"]) return payload except jwt.ExpiredSignatureError: return None except jwt.InvalidTokenError: return None

#-------------------------
#ENDPOINTS
#-------------------------

@app.post("/api/signup") async def signup(response: Response, username: str = Form(...), password: str = Form(...)): res = supabase.from_("users").select("*").eq("username", username).execute() user_exists = res.data

if user_exists:...
@app.post("/api/login") async def login(response: Response, username: str = Form(...), password: str = Form(...)): res = supabase.from_("users").select("*").eq("username", username).execute() user = res.data

if not user:...
@app.get("/api/profile") async def get_profile(request: Request): token = request.cookies.get("token") if not token: raise HTTPException(status_code=401, detail="Tidak terautentikasi")

payload = decode_jwt_token(token)...
@app.post("/api/submit_quiz") async def submit_quiz(request: Request, quiz_name: str = Form(...), score: int = Form(...)): token = request.cookies.get("token") if not token: raise HTTPException(status_code=401, detail="Tidak terautentikasi")

payload = decode_jwt_token(token)...
@app.get("/api/leaderboard") async def leaderboard(): res = supabase.rpc("get_leaderboard").execute() rows = res.data

return {...
@app.get("/health") async def health(): return {"status": "ok", "time": datetime.utcnow().isoformat()}




