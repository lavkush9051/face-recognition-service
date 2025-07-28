from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.models import AppUser, Employee
from app.database import SessionLocal
from app.auth import verify_password, get_password_hash, create_access_token

router = APIRouter()

class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.post("/signup")
def signup(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(AppUser).filter(AppUser.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists.")
    hashed_pwd = get_password_hash(user.password)
    new_user = AppUser(username=user.username, hashed_password=hashed_pwd)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User created successfully"}

@router.post("/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(AppUser).filter(AppUser.username == user.username).first()
    if not db_user or not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"username": db_user.username})

    # Fetch the employee record
    employee = db.query(Employee).filter(Employee.emp_id == db_user.app_emp_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    # Return token AND essential employee info
    return {
        "access_token": token,
        "token_type": "bearer",
        "employee": {
            "emp_id": employee.emp_id,
            "emp_name": employee.emp_name,
            "emp_department": employee.emp_department,
            "emp_designation": employee.emp_designation,
            "emp_l1": employee.emp_l1,
            "emp_l2": employee.emp_l2,
            "emp_gender": employee.emp_gender,
            "emp_address": employee.emp_address,
            "emp_joining_date": employee.emp_joining_date,
            "emp_email": employee.emp_email,
            "emp_contact": employee.emp_contact,
            "emp_marital_status": employee.emp_marital_status,
            "emp_nationality": employee.emp_nationality,
            "emp_pan_no": employee.emp_pan_no,
            "emp_weekoff": employee.emp_weekoff
            # ...any other fields you want...
        }
    }