# app/main.py

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from app.face_engine import FaceEngine
from app.storage import save_user, get_all_users
from app.utils import is_match
from app.database import SessionLocal
from app.models import FaceUser, Base
from sqlalchemy.orm import Session
from app.auth_routes import router as auth_router

import numpy as np

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # You can restrict this to ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

engine = FaceEngine()

@app.post("/register")
async def register(name: str = Form(...), files: List[UploadFile] = File(...)):
    session: Session = SessionLocal()
    # Check for duplicate name
    existing_user = session.query(FaceUser).filter(FaceUser.name == name).first()
    if existing_user:
        session.close()
        return {"status": "failed", "reason": f"User '{name}' already exists."}

    descriptors = []

    for file in files:
        content = await file.read()
        desc = engine.extract_descriptor(content)
        if desc is not None:
            descriptors.append(desc.tolist())

    if not descriptors:
        session.close()
        return {"status": "failed", "reason": "No valid faces detected"}

    for desc in descriptors:
        session.add(FaceUser(name=name, embedding=desc))

    session.commit()
    session.close()

    return {"status": "success", "user": name, "registered_faces": len(descriptors)}


@app.post("/verify")
async def verify(file: UploadFile = File(...)):
    content = await file.read()
    live_descriptor = engine.extract_descriptor(content)
    if live_descriptor is None:
        return {"status": "failed", "reason": "No face detected"}

    session: Session = SessionLocal()
    users = session.query(FaceUser).all()

    best_match = None
    lowest_distance = float("inf")

    for user in users:
        db_desc = np.array(user.embedding)
        distance = np.linalg.norm(live_descriptor - db_desc)
        print(f"[LOG] Compared with {user.name} → Distance: {distance:.4f}")

        if distance < 0.75:
            session.close()
            return {
                "status": "success",
                "user": user.name,
                "distance": round(distance, 4)
            }

        if distance < lowest_distance:
            lowest_distance = distance
            best_match = user.name

    session.close()

    return {
        "status": "failed",
        "reason": "No match below threshold",
        "closest_match": best_match,
        "closest_distance": round(lowest_distance, 4)
    }

