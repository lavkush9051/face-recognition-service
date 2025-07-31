# app/main.py
import calendar
from fastapi import Body, HTTPException, Query
from fastapi import FastAPI, File, UploadFile, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List
#from app.face_engine import FaceEngine
from app.storage import save_user, get_all_users, get_all_employees
from app.utils import is_match
from app.database import SessionLocal
from app.models import ClockInClockOut, FaceUser, Base, Employee, LeaveRequest, AttendanceRequest, LeaveType
from sqlalchemy.orm import Session
from app.auth_routes import router as auth_router
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from .database import get_db
from datetime import date, datetime

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

#engine = FaceEngine()

# @app.post("/register")
# async def register(name: str = Form(...), files: List[UploadFile] = File(...)):
#     session: Session = SessionLocal()
#     # Check for duplicate name
#     existing_user = session.query(FaceUser).filter(FaceUser.name == name).first()
#     if existing_user:
#         session.close()
#         return {"status": "failed", "reason": f"User '{name}' already exists."}

#     descriptors = []

#     for file in files:
#         content = await file.read()
#         desc = engine.extract_descriptor(content)
#         if desc is not None:
#             descriptors.append(desc.tolist())

#     if not descriptors:
#         session.close()
#         return {"status": "failed", "reason": "No valid faces detected"}

#     for desc in descriptors:
#         session.add(FaceUser(name=name, embedding=desc))

#     session.commit()
#     session.close()

#     return {"status": "success", "user": name, "registered_faces": len(descriptors)}

# Verify and clockin endpoint
# @app.post("/verify")
# async def verify(
#     file: UploadFile = File(...),
#     face_user_emp_id: str = Form(...),
# ):
#     content = await file.read()
#     live_descriptor = engine.extract_descriptor(content)
#     if live_descriptor is None:
#         return {"status": "failed", "reason": "No face detected"}

#     session: Session = SessionLocal()
#     users = session.query(FaceUser).filter(FaceUser.face_user_emp_id == face_user_emp_id).all()
#     if not users:
#         session.close()
#         return {"status": "failed", "reason": "User not found"}

#     best_match = None
#     lowest_distance = float("inf")

#     for user in users:
#         db_desc = np.array(user.embedding)
#         distance = np.linalg.norm(live_descriptor - db_desc)
#         print(f"[LOG] Compared with {user.name} → Distance: {distance:.4f}")

#         if distance < 0.75:
#             # --- CLOCK IN LOGIC START ---
#             # Check if today's clock-in already exists
#             today = date.today()
#             clockin_exists = (
#                 session.query(ClockInClockOut)
#                 .filter(
#                     ClockInClockOut.cct_emp_id == int(face_user_emp_id),
#                     ClockInClockOut.cct_date == today,
#                     ClockInClockOut.cct_clockin_time != None  # has a value
#                 )
#                 .first()
#             )
#             if not clockin_exists:
#                 now = datetime.now().time()
#                 new_clockin = ClockInClockOut(
#                     cct_emp_id=int(face_user_emp_id),
#                     cct_date=today,
#                     cct_clockin_time=now,
#                     # You may set cct_clockout_time=None by default or leave it out if nullable
#                 )
#                 session.add(new_clockin)
#                 session.commit()
#             # --- CLOCK IN LOGIC END ---
#             session.close()
#             return {
#                 "status": "success",
#                 "user": user.name,
#                 "distance": round(distance, 4)
#             }

#         if distance < lowest_distance:
#             lowest_distance = distance
#             best_match = user.name

#     session.close()

#     return {
#         "status": "failed",
#         "reason": "Face does not match logged-in user",
#         "closest_match": best_match,
#         "closest_distance": round(lowest_distance, 4)
#     }

#clockout endpoint
from fastapi import Request
@app.put("/api/clockout")
async def clock_out(request: Request):
    data = await request.json()
    print("Raw body:", data)
    emp_id = data.get("emp_id")
    session: Session = SessionLocal()
    today = date.today()
    now = datetime.now().time()
    try:
        # Find today's clock-in
        record = (
            session.query(ClockInClockOut)
            .filter(
                ClockInClockOut.cct_emp_id == emp_id,
                ClockInClockOut.cct_date == today
            )
            .first()
        )
        if not record:
            session.close()
            return {"status": "failed", "error": "No clock-in found for today"}
        # Update clockout time every time
        record.cct_clockout_time = now
        session.commit()
        session.close()
        return {"status": "success", "clockout_time": str(now)}
    except Exception as e:
        session.rollback()
        session.close()
        return {"status": "failed", "error": str(e)}

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
def get_all_leave_requests(admin_id: int = Query(...)):
    session = SessionLocal()
    # Filter: Show requests where admin is L1 or L2 manager
    results = session.query(
        LeaveRequest,
        Employee.emp_name,
        Employee.emp_department,
        Employee.emp_designation
    ).join(Employee, LeaveRequest.leave_req_emp_id == Employee.emp_id
    ).filter(
       (
            (LeaveRequest.leave_req_l1_id == admin_id)
        ) | (
            (LeaveRequest.leave_req_l2_id == admin_id) &
            (LeaveRequest.leave_req_l1_status == "Approved")
        )
    ).all()
    session.close()

    leave_requests = []
    for lr, emp_name, emp_department, emp_designation in results:
        lr_dict = jsonable_encoder(lr)
        lr_dict["emp_name"] = emp_name
        lr_dict["emp_department"] = emp_department
        lr_dict["emp_designation"] = emp_designation
        leave_requests.append(lr_dict)
    return JSONResponse(content=leave_requests)

# For Leave Request L1 Action

# @app.put("/api/leave-request/l1-action")
# async def l1_leave_action(
#     leave_req_id: int = Body(...),
#     action: str = Body(...)  # "approve" or "reject"
# ):
#     session: Session = SessionLocal()
#     try:
#         req = session.query(LeaveRequest).filter(LeaveRequest.leave_req_id == leave_req_id).first()
#         if not req:
#             session.close()
#             return JSONResponse(status_code=404, content={"error": "Leave request not found"})
#         if action == "approve":
#             req.leave_req_l1_status = "Approved"
#             req.leave_req_status = "L1 Approved"
#         elif action == "reject":
#             req.leave_req_l1_status = "Rejected"
#             req.leave_req_status = "Rejected"
#         session.commit()
#         session.close()
#         return {"status": "success"}
#     except Exception as e:
#         session.rollback()
#         session.close()
#         return JSONResponse(status_code=500, content={"status": "failed", "error": str(e)})

# # For L2 Leave Requests

# @app.put("/api/leave-request/l2-action")
# async def l2_leave_action(
#     leave_req_id: int = Body(...),
#     action: str = Body(...)  # "approve" or "reject"
# ):
#     session: Session = SessionLocal()
#     try:
#         req = session.query(LeaveRequest).filter(LeaveRequest.leave_req_id == leave_req_id).first()
#         if not req:
#             session.close()
#             return JSONResponse(status_code=404, content={"error": "Leave request not found"})
#         if action == "approve":
#             req.leave_req_l2_status = "Approved"
#             req.leave_req_status = "Approved"
#         elif action == "reject":
#             req.leave_req_l2_status = "Rejected"
#             req.leave_req_status = "Rejected"
#         session.commit()
#         session.close()
#         return {"status": "success"}
#     except Exception as e:
#         session.rollback()
#         session.close()
#         return JSONResponse(status_code=500, content={"status": "failed", "error": str(e)})

@app.put("/api/leave-request/action")
async def leave_action(
    leave_req_id: int = Body(...),
    action: str = Body(...),            # "approve" or "reject"
    admin_id: int = Body(...)
):
    session: Session = SessionLocal()
    try:
        req = session.query(LeaveRequest).filter(LeaveRequest.leave_req_id == leave_req_id).first()
        if not req:
            session.close()
            return JSONResponse(status_code=404, content={"error": "Leave request not found"})

        # Check if admin is L1 or L2
        if req.leave_req_l1_id == admin_id:
            # L1 manager action
            if action == "approve":
                req.leave_req_l1_status = "Approved"
                req.leave_req_status = "L1 Approved"
            elif action == "reject":
                req.leave_req_l1_status = "Rejected"
                req.leave_req_status = "Rejected"
        elif req.leave_req_l2_id == admin_id:
            # Only L2 can approve after L1 approved
            if req.leave_req_l1_status != "Approved":
                session.close()
                return JSONResponse(status_code=403, content={"error": "L1 must approve before L2 can act"})
            if action == "approve":
                req.leave_req_l2_status = "Approved"
                req.leave_req_status = "Approved"
            elif action == "reject":
                req.leave_req_l2_status = "Rejected"
                req.leave_req_status = "Rejected"
        else:
            session.close()
            return JSONResponse(status_code=403, content={"error": "You are not authorized to act on this request"})

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


# For Leave Request Creation
@app.post("/api/leave-request")
async def create_leave_request(
    emp_id: int = Form(...),
    leave_type: str = Form(...),
    leave_from_dt: str = Form(...),
    leave_to_dt: str = Form(...),
    leave_reason: str = Form(...),
):
    session: Session = SessionLocal()
    try:
        # Lookup L1 and L2 for this employee
        emp = session.query(Employee).filter(Employee.emp_id == emp_id).first()
        if not emp:
            session.close()
            raise HTTPException(status_code=404, detail="Employee not found")

        from_date = datetime.strptime(leave_from_dt, "%Y-%m-%d").date()
        to_date = datetime.strptime(leave_to_dt, "%Y-%m-%d").date()

        leave_req = LeaveRequest(
            leave_req_emp_id=emp_id,
            leave_req_type=leave_type,
            leave_req_from_dt=from_date,
            leave_req_to_dt=to_date,
            leave_req_reason=leave_reason,
            leave_req_status="Pending",
            leave_req_l1_status="Pending",
            leave_req_l2_status="Pending",
            leave_req_l1_id=emp.emp_l1,   # <-- Added!
            leave_req_l2_id=emp.emp_l2,   # <-- Added!
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


@app.get("/api/attendance")
def get_attendance(
    emp_id: int = Query(...),
    start: str = Query(...),
    end: str = Query(...)
):
    session: Session = SessionLocal()
    try:
        # Attendance data for month
        records = session.query(ClockInClockOut).filter(
            ClockInClockOut.cct_emp_id == emp_id,
            ClockInClockOut.cct_date >= start,
            ClockInClockOut.cct_date <= end
        ).all()

        present_days = []
        total_working_mins = 0
        total_late_mins = 0
        late_standard = datetime.strptime("09:00", "%H:%M").time()
        for rec in records:
            # Format clockin/clockout as string
            clockin_str = rec.cct_clockin_time.strftime("%I:%M %p") if rec.cct_clockin_time else "-"
            clockout_str = rec.cct_clockout_time.strftime("%I:%M %p") if rec.cct_clockout_time else "-"
            present_days.append({
                "date": rec.cct_date.strftime("%Y-%m-%d"),
                "clockIn": clockin_str,
                "clockOut": clockout_str
            })
            # Average working hours
            if rec.cct_clockin_time and rec.cct_clockout_time:
                t1 = datetime.combine(datetime.today(), rec.cct_clockin_time)
                t2 = datetime.combine(datetime.today(), rec.cct_clockout_time)
                total_working_mins += max(0, int((t2 - t1).total_seconds() / 60))
            # Average late by
            if rec.cct_clockin_time:
                late = (
                    datetime.combine(datetime.today(), rec.cct_clockin_time) -
                    datetime.combine(datetime.today(), late_standard)
                ).total_seconds() / 60
                total_late_mins += max(0, late)

        # Calculate working/absent
        num_present = len(present_days)
        days_in_month = (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(start, "%Y-%m-%d")).days + 1
        absent = 0
        year, month = int(start[:4]), int(start[5:7])
        total_working = 0
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            date_obj = datetime(year, month, day)
            if date_obj.weekday() < 5:  # Mon-Fri
                total_working += 1
        absent = total_working - num_present

        average_working = "-"
        average_late = "-"
        if num_present > 0:
            avg_mins = total_working_mins / num_present
            h, m = int(avg_mins // 60), int(avg_mins % 60)
            average_working = f"{h}h {m}m"
            avg_late = total_late_mins / num_present
            if avg_late < 1:
                average_late = "On Time"
            else:
                lh, lm = int(avg_late // 60), int(avg_late % 60)
                average_late = f"{lh}h {lm}m"

        # Get shift details from employee table
        emp = session.query(Employee).filter(Employee.emp_id == emp_id).first()
        shift = getattr(emp, "emp_shift", "-") if emp else "-"

        return {
            "attendance": present_days,
            "holidays": [],  # You can fill this if you have holiday table
            "absent": absent,
            "average_working": average_working,
            "average_late": average_late,
            "shift": shift
        }
    finally:
        session.close()


@app.get("/api/leave-types")
def get_leave_types(db: Session = Depends(get_db)):
    leave_types = db.query(LeaveType).all()
    # Convert to dict
    result = [
        {
            "type": l.lt_leave_type,
            "abrev": l.lt_abrev,
            "total": l.lt_total
        }
        for l in leave_types
    ]
    return {"leave_types": result}      