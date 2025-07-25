# app/main.py
from fastapi import Body, HTTPException, Query
from fastapi import FastAPI, File, UploadFile, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from app.face_engine import FaceEngine
from app.storage import save_user, get_all_users, get_all_employees
from app.utils import is_match
from app.database import SessionLocal
from app.models import FaceUser, Base, Employee, LeaveRequest, AttendanceRequest
from sqlalchemy.orm import Session
from app.auth_routes import router as auth_router
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from .database import get_db
from datetime import datetime

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

# Verify endpoint
@app.post("/verify")
async def verify(file: UploadFile = File(...), username:str = Form(...)):

    content = await file.read()
    live_descriptor = engine.extract_descriptor(content)
    if live_descriptor is None:
        return {"status": "failed", "reason": "No face detected"}

    session: Session = SessionLocal()
     # Only select records with this username!
    users = session.query(FaceUser).filter(FaceUser.name == username).all()

    #users = session.query(FaceUser).all()
    if not users:
        session.close()
        return {"status": "failed", "reason": "User not found"}

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
        "reason": "Face does not match logged-in user",
        "closest_match": best_match,
        "closest_distance": round(lowest_distance, 4)
    }

# API Endpoints for Employees
@app.get("/api/employees")
async def api_get_all_employees():
    session: Session = SessionLocal()
    employees = get_all_employees(session)
    session.close()
    # Convert SQLAlchemy objects to dicts
    employee_dicts = [jsonable_encoder(emp) for emp in employees]
    return JSONResponse(content=employee_dicts)

# For Employee Details by ID
@app.get("/api/employee/{emp_id}")
def get_employee(emp_id: int):
    session = SessionLocal()
    emp = session.query(Employee).filter(Employee.emp_id == emp_id).first()
    session.close()
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return {
        "emp_id": emp.emp_id,
        "emp_name": emp.emp_name,
        "emp_department": emp.emp_department,
        "emp_designation": emp.emp_designation,
        # add any more fields you want
    }

# For bulk/single update
@app.put("/api/employees/weekoff")
async def update_employees_weekoff(
    emp_ids: list[int] = Body(...),
    weekoff: str = Body(...)
):
    session: Session = SessionLocal()
    try:
        # Update all given emp_ids
        updated = session.query(Employee).filter(Employee.emp_id.in_(emp_ids)).update(
            {Employee.emp_weekoff: weekoff}, synchronize_session=False
        )
        session.commit()
        session.close()
        return {"status": "success", "updated": updated}
    except Exception as e:
        session.rollback()
        session.close()
        return JSONResponse(status_code=500, content={"status": "failed", "error": str(e)})
    
# For Leave Requests

@app.get("/api/leave-requests")
def get_all_leave_requests():
    session = SessionLocal()
    # Join LeaveRequest and Employee to get leave info + employee info
    results = session.query(
        LeaveRequest,
        Employee.emp_name,
        Employee.emp_department,
        Employee.emp_designation
    ).join(Employee, LeaveRequest.leave_req_emp_id == Employee.emp_id).all()
    session.close()

    # Convert joined results to a list of dicts
    leave_requests = []
    for lr, emp_name, emp_department, emp_designation in results:
        lr_dict = jsonable_encoder(lr)
        lr_dict["emp_name"] = emp_name
        lr_dict["emp_department"] = emp_department
        lr_dict["emp_designation"] = emp_designation
        leave_requests.append(lr_dict)
    return JSONResponse(content=leave_requests)

# For Leave Request L1 Action

@app.put("/api/leave-request/l1-action")
async def l1_leave_action(
    leave_req_id: int = Body(...),
    action: str = Body(...)  # "approve" or "reject"
):
    session: Session = SessionLocal()
    try:
        req = session.query(LeaveRequest).filter(LeaveRequest.leave_req_id == leave_req_id).first()
        if not req:
            session.close()
            return JSONResponse(status_code=404, content={"error": "Leave request not found"})
        if action == "approve":
            req.leave_req_l1_status = "Approved"
            req.leave_req_status = "L1 Approved"
        elif action == "reject":
            req.leave_req_l1_status = "Rejected"
            req.leave_req_status = "Rejected"
        session.commit()
        session.close()
        return {"status": "success"}
    except Exception as e:
        session.rollback()
        session.close()
        return JSONResponse(status_code=500, content={"status": "failed", "error": str(e)})

# For L2 Leave Requests

@app.put("/api/leave-request/l2-action")
async def l2_leave_action(
    leave_req_id: int = Body(...),
    action: str = Body(...)  # "approve" or "reject"
):
    session: Session = SessionLocal()
    try:
        req = session.query(LeaveRequest).filter(LeaveRequest.leave_req_id == leave_req_id).first()
        if not req:
            session.close()
            return JSONResponse(status_code=404, content={"error": "Leave request not found"})
        if action == "approve":
            req.leave_req_l2_status = "Approved"
            req.leave_req_status = "Approved"
        elif action == "reject":
            req.leave_req_l2_status = "Rejected"
            req.leave_req_status = "Rejected"
        session.commit()
        session.close()
        return {"status": "success"}
    except Exception as e:
        session.rollback()
        session.close()
        return JSONResponse(status_code=500, content={"status": "failed", "error": str(e)})
    
# For Attendance Requests
    
@app.get("/api/attendance-requests")
def get_all_attendance_requests():
    session = SessionLocal()
    # Join AttendanceRequest with Employee for employee info
    results = session.query(
        AttendanceRequest,
        Employee.emp_name,
        Employee.emp_department,
        Employee.emp_designation
    ).join(Employee, AttendanceRequest.art_emp_id == Employee.emp_id).all()
    session.close()

    attendance_requests = []
    for ar, emp_name, emp_department, emp_designation in results:
        ar_dict = jsonable_encoder(ar)
        ar_dict["emp_name"] = emp_name
        ar_dict["emp_department"] = emp_department
        ar_dict["emp_designation"] = emp_designation
        attendance_requests.append(ar_dict)
    return JSONResponse(content=attendance_requests)


# For Attendance Requests by Employee ID

@app.get("/api/leave-requests/{emp_id}")
def get_leave_requests(emp_id: int, db: Session = Depends(get_db)):
    requests = (
        db.query(LeaveRequest, Employee)
        .join(Employee, LeaveRequest.leave_req_emp_id == Employee.emp_id)
        .filter(LeaveRequest.leave_req_emp_id == emp_id)
        .order_by(LeaveRequest.leave_req_from_dt.desc())
        .all()
    )
    print(f"[DEBUG] Found {len(requests)} leave requests for emp_id {emp_id}")
    result = []
    for lr, emp in requests:
        result.append({
            "leave_req_id": lr.leave_req_id,
            "leave_req_emp_id": lr.leave_req_emp_id,
            "emp_name": emp.emp_name,
            "emp_department": emp.emp_department,
            "leave_req_type": lr.leave_req_type,
            "leave_req_from_dt": str(lr.leave_req_from_dt),
            "leave_req_to_dt": str(lr.leave_req_to_dt),
            "leave_req_reason": lr.leave_req_reason,
            "leave_req_status": lr.leave_req_status,
            "leave_req_l1_status": lr.leave_req_l1_status,
            "leave_req_l2_status": lr.leave_req_l2_status,
        })
    return result



@app.post("/api/leave-request")
async def create_leave_request(
    emp_id: int = Form(...),
    leave_type: str = Form(...),
    leave_from_dt: str = Form(...),
    leave_to_dt: str = Form(...),
    leave_reason: str = Form(...)
   # evidence: UploadFile = File(None)
):
    session: Session = SessionLocal()
    try:
        # Optionally save evidence file here if uploaded
        #evidence_filename = evidence.filename if evidence else None

        from_date = datetime.strptime(leave_from_dt, "%Y-%m-%d").date()
        to_date = datetime.strptime(leave_to_dt, "%Y-%m-%d").date()


        leave_req = LeaveRequest(
            leave_req_emp_id=emp_id,
            leave_req_type=leave_type,
            leave_req_from_dt=leave_from_dt,
            leave_req_to_dt=leave_to_dt,
            leave_req_reason=leave_reason,
            leave_req_status="Pending",
            leave_req_l1_status="Pending",
            leave_req_l2_status="Pending",
            # Add: leave_req_evidence=evidence_filename (if column exists)
        )
        session.add(leave_req)
        session.commit()
        leave_req_id = leave_req.leave_req_id 
        session.close()
        return {"status": "success", "leave_req_id": leave_req_id}
    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/leave-requests/{leave_req_id}")
def delete_leave_request(leave_req_id: int):
    session: Session = SessionLocal()
    try:
        leave_req = session.query(LeaveRequest).filter(LeaveRequest.leave_req_id == leave_req_id).first()
        if not leave_req:
            session.close()
            raise HTTPException(status_code=404, detail="Leave request not found")
        session.delete(leave_req)
        session.commit()
        session.close()
        return {"status": "success"}
    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(status_code=500, detail=str(e))
    

@app.post("/api/attendance-regularization")
def create_attendance_request(
    emp_id: int = Body(...),
    date: str = Body(...),          # 'YYYY-MM-DD'
    clock_in: str = Body(...),      # 'HH:MM' (24-hour)
    clock_out: str = Body(...),     # 'HH:MM'
    reason: str = Body(...),
):
    session: Session = SessionLocal()
    try:
        att_date = datetime.strptime(date, "%Y-%m-%d").date()
        clock_in_time = datetime.strptime(clock_in, "%H:%M").time()
        clock_out_time = datetime.strptime(clock_out, "%H:%M").time()
        attendance = AttendanceRequest(
            art_emp_id=emp_id,
            art_date=att_date,
            art_clockin_time=clock_in_time,
            art_clockout_time=clock_out_time,
            art_reason=reason,
            art_status="Pending",
            art_l1_status="Pending",
            art_l2_status="Pending",
        )
        session.add(attendance)
        session.commit()
        att_id = attendance.art_id
        session.close()
        return {"status": "success", "art_id": att_id}
    except Exception as e:
        session.rollback()
        session.close()
        raise HTTPException(status_code=500, detail=str(e))


# For Attendance Request L1 Action

@app.put("/api/attendance-request/l1-action")
async def l1_attendance_action(
    art_id: int = Body(...),
    action: str = Body(...)
):
    session = SessionLocal()
    try:
        req = session.query(AttendanceRequest).filter(AttendanceRequest.art_id == art_id).first()
        if not req:
            session.close()
            return JSONResponse(status_code=404, content={"error": "Attendance request not found"})
        if action == "approve":
            req.art_l1_status = "Approved"
            req.art_status = "L1 Approved"
        elif action == "reject":
            req.art_l1_status = "Rejected"
            req.art_status = "Rejected"
        else:
            session.close()
            return JSONResponse(status_code=400, content={"error": "Invalid action"})
        session.commit()
        session.close()
        return {"status": "success"}
    except Exception as e:
        session.rollback()
        session.close()
        return JSONResponse(status_code=500, content={"status": "failed", "error": str(e)})
    
# For Attendance Request L2 Action

@app.put("/api/attendance-request/l2-action")
async def l2_attendance_action(
    art_id: int = Body(...),
    action: str = Body(...)
):
    session = SessionLocal()
    try:
        req = session.query(AttendanceRequest).filter(AttendanceRequest.art_id == art_id).first()
        if not req:
            session.close()
            return JSONResponse(status_code=404, content={"error": "Attendance request not found"})
        if action == "approve":
            req.art_l2_status = "Approved"
            req.art_status = "Approved"
        elif action == "reject":
            req.art_l2_status = "Rejected"
            req.art_status = "Rejected"
        else:
            session.close()
            return JSONResponse(status_code=400, content={"error": "Invalid action"})
        session.commit()
        session.close()
        return {"status": "success"}
    except Exception as e:
        session.rollback()
        session.close()
        return JSONResponse(status_code=500, content={"status": "failed", "error": str(e)})
    

@app.get("/api/reporting-levels")
def get_reporting_levels(emp_id: int = Query(...), l1_id: int = Query(...), l2_id: int = Query(...)):
    session: Session = SessionLocal()
    try:
        employees = session.query(Employee).filter(Employee.emp_id.in_([emp_id, l1_id, l2_id])).all()
        if not employees or len(employees) < 3:
            raise HTTPException(status_code=404, detail="Some users not found")

        # Map by emp_id for clarity
        user_map = {emp.emp_id: emp for emp in employees}

        def to_dict(emp, role):
            return {
                "name": emp.emp_name,
                "designation": emp.emp_designation,
                "email": getattr(emp, "emp_email", "-"),
                "mobile": getattr(emp, "emp_contact", "-"),
                "department": getattr(emp, "emp_department", "-"),
                "avatarColor": "#4F8CFD" if role == "Employee" else "#FFA548" if role == "L1 Manager" else "#53D18A"
            }

        return {
            "employee": to_dict(user_map[emp_id], "Employee"),
            "l1": to_dict(user_map[l1_id], "L1 Manager"),
            "l2": to_dict(user_map[l2_id], "L2 Manager")
        }
    finally:
        session.close()