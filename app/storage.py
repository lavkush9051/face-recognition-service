# app/storage.py
from sqlalchemy.orm import Session
from app.models import Employee

stored_faces = {}  # {username: [descriptors]}

def save_user(name, descriptors):
    stored_faces[name] = descriptors

def get_all_users():
    return stored_faces.items()

def get_all_employees(db: Session):
    return db.query(Employee).all()
