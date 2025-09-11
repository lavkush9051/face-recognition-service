# app/main.py
import calendar
from operator import and_
from fastapi import Body, HTTPException, Query
from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from app.face_engine import FaceEngine
from app.storage import save_user, get_all_users, get_all_employees
from app.utils import is_match
from app.database import SessionLocal
from app.models import ClockInClockOut, EmpShift, FaceUser, Base, Employee, LeaveBalance, LeaveRequest, AttendanceRequest, LeaveType, EmpShift
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.auth_routes import router as auth_router
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from .database import get_db
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
IST = ZoneInfo("Asia/Kolkata")


import numpy as np

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins= ["*"],#["https://attendease-app.vercel.app/", "https://attendease-8hr581l66-lavkushandsingh-4726s-projects.vercel.app/","14.143.212.6:0","http://localhost:3000"],  # You can restrict this to ["http://localhost:5173"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CLOCKIN_THRESHOLD = 0.75 

app.include_router(auth_router)

engine = FaceEngine()

# @app.middleware("http")
# async def log_requests(request: Request, call_next):
#     print(f"[REQ] {request.method} {request.url}")
#     response = await call_next(request)
#     print(f"[RES] {response.status_code} {request.method} {request.url}")
#     return response


# Initialize DB tables

@app.post("/api/register")
async def register_faces(
    emp_id: int = Form(...),
    name: str = Form(...),
    files: List[UploadFile] = File(...)
):
    session: Session = SessionLocal()
    try:
        # 1) must be exactly 4 files
        if not files or len(files) != 4:
            return JSONResponse(
                status_code=400,
                content={"status": "failed", "reason": "Exactly 4 images are required."}
            )

        # 2) allow register only if this emp has no face rows yet
        already = session.query(FaceUser).filter(FaceUser.face_user_emp_id == emp_id).first()
        if already:
            return JSONResponse(
                status_code=409,
                content={"status": "failed", "reason": "Faces already registered for this employee."}
            )

        descriptors = []
        for file in files:
            content = await file.read()
            desc = engine.extract_descriptor(content)  # returns np.ndarray or None
            if desc is not None:
                # store as plain Python list (for ARRAY(Float))
                descriptors.append(desc.tolist())

        # need all 4 to be valid
        if len(descriptors) < 4:
            return JSONResponse(
                status_code=400,
                content={"status": "failed", "reason": f"Detected only {len(descriptors)} valid face(s). Please upload 4 clear face images."}
            )

        # 3) insert 4 rows for the same emp (one per embedding)
        for desc in descriptors:
            session.add(FaceUser(
                name=name,
                face_user_emp_id=emp_id,
                embedding=desc
            ))

        session.commit()
        return {"status": "success", "user": name, "emp_id": emp_id, "registered_faces": len(descriptors)}
    except Exception as e:
        session.rollback()
        return JSONResponse(status_code=500, content={"status": "failed", "error": str(e)})
    finally:
        session.close()


# Verify and clockin endpoint
@app.post("/api/clockin") # /verify
async def verify(
    file: UploadFile = File(...),
    face_user_emp_id: str = Form(...),
    shift : str = Form(...),
):
    content = await file.read()
    live_descriptor = engine.extract_descriptor(content)
    if live_descriptor is None:
        return {"status": "failed", "reason": "No face detected"}

    session: Session = SessionLocal()
    now_ist = datetime.now(IST)
    today_ist = now_ist.date()
    time_ist = now_ist.time().replace(microsecond=0)

    users = session.query(FaceUser).filter(FaceUser.face_user_emp_id == face_user_emp_id).all()
    if not users:
        session.close()
        return {"status": "failed", "reason": "User not found"}

    best_match = None
    lowest_distance = float("inf")

    #check user's shift for clockin
    emp_shift = session.query(EmpShift).filter(EmpShift.est_shift_abbrv == shift).first()
    if not emp_shift:
        return {"status": "failed", "reason": "Shift not found"}

    now_ist = datetime.now(IST)
    if not within_clockin_window(now_ist, emp_shift.est_shift_start_time, minutes=15):
        return {"status": "failed", "reason": "Clock-in not allowed outside ±15 min window"}

    for user in users:
        db_desc = np.array(user.embedding)
        distance = np.linalg.norm(live_descriptor - db_desc)
        print(f"[LOG] Compared with {user.name} → Distance: {distance:.4f}")

        if distance < 0.75:
            # --- CLOCK IN LOGIC START ---
            # Check if today's clock-in already exists
            # today = date.today()
            
            clockin_exists = (
                session.query(ClockInClockOut)
                .filter(
                    ClockInClockOut.cct_emp_id == int(face_user_emp_id),
                    ClockInClockOut.cct_date == today_ist,
                    ClockInClockOut.cct_clockin_time != None  # has a value
                )
                .first()
            )
            if not clockin_exists:
                
                # now = datetime.now().time()
                new_clockin = ClockInClockOut(
                    cct_emp_id=int(face_user_emp_id),
                    cct_date=today_ist,
                    cct_clockin_time=time_ist,
                    cct_shift_abbrv = shift,
                    # You may set cct_clockout_time=None by default or leave it out if nullable
                )
                session.add(new_clockin)
                session.commit()
            # --- CLOCK IN LOGIC END ---
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

def within_clockin_window(now_ist: datetime, shift_start_time, minutes: int = 15) -> bool:
    """
    True if now_ist is within [shift_start - minutes, shift_start + minutes].
    Handles windows that cross midnight (e.g., 00:05 start).
    """
    # anchor shift start to *today* in IST
    start_today = datetime.combine(now_ist.date(), shift_start_time).replace(tzinfo=IST)
    window = timedelta(minutes=minutes)
    ws_today = start_today - window
    we_today = start_today + window

    # also consider the window for *tomorrow* (covers early clock-in before midnight for a 00:xx shift)
    start_tom = start_today + timedelta(days=1)
    ws_tom = start_tom - window
    we_tom = start_tom + window

    return (ws_today <= now_ist <= we_today) or (ws_tom <= now_ist <= we_tom)

#clockout endpoint
from fastapi import Request
@app.put("/api/clockout")
async def clock_out(request: Request):
    data = await request.json()
    print("Raw body:", data)
    emp_id = data.get("emp_id")
    session: Session = SessionLocal()
    #today = date.today()
    #now = datetime.now().time()
    IST = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(IST)
    today_ist = now_ist.date()
    time_ist = now_ist.time().replace(microsecond=0)
    
    try:
        # Find today's clock-in
        record = (
            session.query(ClockInClockOut)
            .filter(
                ClockInClockOut.cct_emp_id == emp_id,
                ClockInClockOut.cct_date == today_ist
            )
            .first()
        )
        if not record:
            session.close()
            return {"status": "failed", "error": "No clock-in found for today"}
        # Update clockout time every time
        record.cct_clockout_time = time_ist
        session.commit()
        session.close()
        return {"status": "success", "clockout_time": str(time_ist)}
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

# @app.put("/api/leave-request/action")
# async def leave_action(
#     leave_req_id: int = Body(...),
#     action: str = Body(...),            # "approve" or "reject"
#     admin_id: int = Body(...)
# ):
#     session: Session = SessionLocal()
#     try:
#         req = session.query(LeaveRequest).filter(LeaveRequest.leave_req_id == leave_req_id).first()
#         if not req:
#             session.close()
#             return JSONResponse(status_code=404, content={"error": "Leave request not found"})

#         # Check if admin is L1 or L2
#         if req.leave_req_l1_id == admin_id:
#             # L1 manager action
#             if action == "approve":
#                 req.leave_req_l1_status = "Approved"
#                 req.leave_req_status = "L1 Approved"
#             elif action == "reject":
#                 req.leave_req_l1_status = "Rejected"
#                 req.leave_req_status = "Rejected"
#         elif req.leave_req_l2_id == admin_id:
#             # Only L2 can approve after L1 approved
#             if req.leave_req_l1_status != "Approved":
#                 session.close()
#                 return JSONResponse(status_code=403, content={"error": "L1 must approve before L2 can act"})
#             if action == "approve":
#                 req.leave_req_l2_status = "Approved"
#                 req.leave_req_status = "Approved"
#             elif action == "reject":
#                 req.leave_req_l2_status = "Rejected"
#                 req.leave_req_status = "Rejected"
#         else:
#             session.close()
#             return JSONResponse(status_code=403, content={"error": "You are not authorized to act on this request"})

#         session.commit()
#         session.close()
#         return {"status": "success"}

#     except Exception as e:
#         session.rollback()
#         session.close()
#         return JSONResponse(status_code=500, content={"status": "failed", "error": str(e)})


#new method with ledger ops
@app.put("/api/leave-request/action")
async def leave_action(
    leave_req_id: int = Body(...),
    action: str = Body(...),      # "approve" or "reject"
    admin_id: int = Body(...),
    remarks: str = Body(...)  # New remarks field
):
    session: Session = SessionLocal()
    try:
        req = session.query(LeaveRequest).filter(LeaveRequest.leave_req_id == leave_req_id).first()
        if not req:
            session.close()
            return JSONResponse(status_code=404, content={"error": "Leave request not found"})

        # Compute qty for ledger ops
        qty = business_days_inclusive(req.leave_req_from_dt, req.leave_req_to_dt)
        emp_id = req.leave_req_emp_id
        ltype = req.leave_req_type

        action = action.lower().strip()
        if action not in ("approve", "reject"):
            session.close()
            return JSONResponse(status_code=400, content={"error": "Invalid action"})

        # L1 action
        if getattr(req, "leave_req_l1_id", None) == admin_id:
            if action == "approve":
                req.leave_req_l1_status = "Approved"
                req.leave_req_status = "L1 Approved"
                # HOLD remains in place (no ledger change)
            else:
                # reject: RELEASE hold
                req.leave_req_l1_status = "Rejected"
                req.leave_req_status = "Rejected"
                ledger_release(session, emp_id, ltype, qty, req.leave_req_id)
            # Add remarks if provided
            if remarks:
                req.remarks = (req.remarks or "") + f"\nL1 ({admin_id}): {remarks}"
    

        # L2 action
        elif getattr(req, "leave_req_l2_id", None) == admin_id:
            if req.leave_req_l1_status != "Approved":
                session.close()
                return JSONResponse(status_code=403, content={"error": "L1 must approve before L2 can act"})

            if action == "approve":
                req.leave_req_l2_status = "Approved"
                req.leave_req_status = "Approved"
                # Finalize: RELEASE HOLD and COMMIT
                ledger_release(session, emp_id, ltype, qty, req.leave_req_id)
                ledger_commit(session, emp_id, ltype, qty, req.leave_req_id)
            else:
                req.leave_req_l2_status = "Rejected"
                req.leave_req_status = "Rejected"
                # Rejection at L2 → RELEASE hold
                ledger_release(session, emp_id, ltype, qty, req.leave_req_id)
            
            # Add remarks if provided
            if remarks:
                req.remarks = (req.remarks or "") + f"\nL2 ({admin_id}): {remarks}"


        else:
            session.close()
            return JSONResponse(status_code=403, content={"error": "You are not authorized to act on this request"})

        session.commit()
        return {"status": "success"}

    except Exception as e:
        session.rollback()
        return JSONResponse(status_code=500, content={"status": "failed", "error": str(e)})
    finally:
        session.close()


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

from fastapi import Query

@app.get("/api/regularization-requests/{emp_id}")
def get_attendance_regularization_requests(
    emp_id: int,
    admin: bool = Query(False),
    db: Session = Depends(get_db),
):
    if not admin:
        # Employee view: same as your original
        requests = (
            db.query(AttendanceRequest, Employee)
            .join(Employee, AttendanceRequest.art_emp_id == Employee.emp_id)
            .filter(AttendanceRequest.art_emp_id == emp_id)
            .order_by(AttendanceRequest.art_date.desc())
            .all()
        )
    else:
        # ADMIN MODE: emp_id here is the admin's employee id
        # L1: can see Pending + Approved where they're L1 approver
        l1_reqs = (
            db.query(AttendanceRequest, Employee)
            .join(Employee, AttendanceRequest.art_emp_id == Employee.emp_id)
            .filter(AttendanceRequest.art_l1_id == emp_id)
            .filter(AttendanceRequest.art_l1_status.in_(["Approved", "Pending"]))
            .order_by(AttendanceRequest.art_date.desc())
            .all()
        )

        # L2: can see only those where L1 is Approved and they're L2 approver
        l2_reqs = (
            db.query(AttendanceRequest, Employee)
            .join(Employee, AttendanceRequest.art_emp_id == Employee.emp_id)
            .filter(AttendanceRequest.art_l2_id == emp_id)
            .filter(AttendanceRequest.art_l1_status == "Approved")
            .order_by(AttendanceRequest.art_date.desc())
            .all()
        )

        # Deduplicate by request id while preserving latest-first order
        dedup: dict[int, tuple[AttendanceRequest, Employee]] = {}
        for ar, emp in l1_reqs + l2_reqs:
            dedup[ar.art_id] = (ar, emp)

        # Maintain date-desc order after dedupe
        requests = sorted(dedup.values(), key=lambda x: x[0].art_date, reverse=True)

    print(f"[DEBUG] Found {len(requests)} regularization requests for emp_id {emp_id} (admin={admin})")

    result = []
    for ar, emp in requests:
        result.append({
            "id": ar.art_id,
            "emp_id": ar.art_emp_id,
            "employee_name": emp.emp_name,
            "emp_department": emp.emp_department,
            "date": str(ar.art_date),
            "clock_in": str(ar.art_clockin_time) if ar.art_clockin_time else "-",
            "clock_out": str(ar.art_clockout_time) if ar.art_clockout_time else "-",
            "reason": ar.art_reason,
            "status": ar.art_status,
            "l1_status": ar.art_l1_status,
            "l2_status": ar.art_l2_status,
        })

    print(f"[DEBUG] Returning {len(result)} regularization requests")
    return result


@app.get("/api/leave-requests/{emp_id}")
def get_leave_requests(
    emp_id: int,
    admin: bool = Query(False),
    db: Session = Depends(get_db)
):
    # If not admin, return as before
    if not admin:
        requests = (
            db.query(LeaveRequest, Employee)
            .join(Employee, LeaveRequest.leave_req_emp_id == Employee.emp_id)
            .filter(LeaveRequest.leave_req_emp_id == emp_id)
            .order_by(LeaveRequest.leave_req_from_dt.desc())
            .all()
        )
    else:
        # ADMIN MODE: emp_id here is the admin's ID!
        # Find all leave requests where this admin is l1 or l2
        l1_reqs = (
            db.query(LeaveRequest, Employee)
            .join(Employee, LeaveRequest.leave_req_emp_id == Employee.emp_id)
            .filter(LeaveRequest.leave_req_l1_id == emp_id)
            .filter(LeaveRequest.leave_req_l1_status.in_(["Approved", "Pending"]))
            .order_by(LeaveRequest.leave_req_from_dt.desc())
            .all()
        )
        l2_reqs = (
            db.query(LeaveRequest, Employee)
            .join(Employee, LeaveRequest.leave_req_emp_id == Employee.emp_id)
            .filter(LeaveRequest.leave_req_l2_id == emp_id)
            .filter(LeaveRequest.leave_req_l1_status == "Approved")  # Only if L1 approved
            .order_by(LeaveRequest.leave_req_from_dt.desc())
            .all()
        )
        # Combine L1 and L2 requests, and remove duplicates (if any)
        requests = list({(lr.leave_req_id, lr, emp) for lr, emp in l1_reqs + l2_reqs})
        # Now unpack tuples
        requests = [(lr, emp) for _, lr, emp in requests]

    print(f"[DEBUG] Found {len(requests)} leave requests for emp_id {emp_id} (admin={admin})")
    result = []
    for lr, emp in requests:
        result.append({
            "id": lr.leave_req_id,
            "emp_id": lr.leave_req_emp_id,
            "employee_name": emp.emp_name,
            "emp_department": emp.emp_department,
            "leave_type_name": lr.leave_req_type,
            "start_date": str(lr.leave_req_from_dt),
            "end_date": str(lr.leave_req_to_dt),
            "reason": lr.leave_req_reason,
            "status": lr.leave_req_status,
            "l1_status": lr.leave_req_l1_status,
            "l2_status": lr.leave_req_l2_status,
            "remarks": lr.remarks or "",
            "applied_date": str(lr.leave_req_applied_dt) if lr.leave_req_applied_dt else "-",
        })
    print(f"[DEBUG] Returning {len(result)} leave requests")
    return result


# For Leave Request Creation
@app.post("/api/leave-request")
async def create_leave_request(
    
    emp_id: int = Form(...),
    leave_type: str = Form(...),
    leave_from_dt: str = Form(...),
    leave_to_dt: str = Form(...),
    leave_reason: str = Form(...),
    leave_applied_dt: str = Form(...),
):
    print(f"[DEBUG] Creating leave request for emp_id {emp_id} from {leave_from_dt} to {leave_to_dt}")
    session: Session = SessionLocal()
    try:
        # Lookup L1 and L2 for this employee
        emp = session.query(Employee).filter(Employee.emp_id == emp_id).first()
        if not emp:
            session.close()
            raise HTTPException(status_code=404, detail="Employee not found")

        from_date = datetime.strptime(leave_from_dt, "%Y-%m-%d").date()
        to_date = datetime.strptime(leave_to_dt, "%Y-%m-%d").date()
        leave_applied_dt = datetime.strptime(leave_applied_dt, "%Y-%m-%d").date()

        # Compute quantity (days). Adjust function if you want to include weekends/holidays.
        print(f"[DEBUG] Calculating leave quantity from {from_date} to {to_date}")
        qty = business_days_inclusive(from_date, to_date)
        if qty <= 0:
            session.close()
            raise HTTPException(status_code=400, detail="Invalid date range")

        # Check available balance snapshot
        print(f"[DEBUG] Checking leave balance for emp_id {emp_id}, type {leave_type}")
        snap = get_balance_snapshot(session, emp_id, leave_type)
        if snap["available"] < qty:
            session.close()
            return JSONResponse(
                status_code=400,
                content={
                    "status": "failed",
                    "error": f"Insufficient balance. Available={snap['available']} required={qty}"
                },
            )

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
            remarks = "",
            leave_req_applied_dt = leave_applied_dt
        )
        session.add(leave_req)
        session.flush()  # to get leave_req.leave_req_id
        print(f"[DEBUG] Created leave_req_id {leave_req.leave_req_id}, recording HOLD in ledger")
        ledger_hold(session, emp_id, leave_type, qty, leave_req.leave_req_id)
        session.commit()
        leave_req_id = leave_req.leave_req_id
        session.close()
        return {"status": "success", "leave_req_id": leave_req_id}
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        # optional: log the stacktrace here
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()



# Map your request leave type → LeaveBalance column name
LEAVE_COL_MAP = {
    "Casual Leave": "lt_casual_leave",
    "Earned Leave": "lt_earned_leave",
    "Half Pay Leave": "lt_half_pay_leave",
    "Medical Leave": "lt_medical_leave",
    "Special Leave": "lt_special_leave",
    "Child Care Leave": "lt_child_care_leave",
    "Parental Leave": "lt_parental_leave",
    # Or if you use abbrevs, map those instead.
}

def business_days_inclusive(start_dt: datetime.date, end_dt: datetime.date) -> float:
    """Simple version: count Mon–Fri only. No holiday table used here."""
    if end_dt < start_dt:
        return 0
    days = 0
    cur = start_dt
    one = timedelta(days=1)
    while cur <= end_dt:
        if cur.weekday() < 5:  # 0=Mon ... 4=Fri
            days += 1
        cur += one
    return float(days)

def get_accrued(db: Session, emp_id: int, leave_type: str) -> float:
    from app.models import LeaveBalance  # adjust import if split
    col = LEAVE_COL_MAP.get(leave_type)
    if not col:
        return 0.0
    row = db.query(LeaveBalance).filter(LeaveBalance.lt_emp_id == emp_id).one_or_none()
    if not row:
        return 0.0
    return float(getattr(row, col) or 0)

def sum_ledger(db: Session, emp_id: int, leave_type: str, action: str) -> float:
    from app.models import LeaveLedger
    total = db.query(func.coalesce(func.sum(LeaveLedger.ll_qty), 0.0))\
              .filter(LeaveLedger.ll_emp_id == emp_id,
                      LeaveLedger.ll_leave_type == leave_type,
                      LeaveLedger.ll_action == action)\
              .scalar()
    return float(total or 0.0)

def get_balance_snapshot(db: Session, emp_id: int, leave_type: str) -> dict:
    accrued = get_accrued(db, emp_id, leave_type)
    held = sum_ledger(db, emp_id, leave_type, "HOLD") - sum_ledger(db, emp_id, leave_type, "RELEASE")
    committed = sum_ledger(db, emp_id, leave_type, "COMMIT")
    available = accrued - committed - max(0.0, held)
    return {"accrued": accrued, "held": max(0.0, held), "committed": committed, "available": available}

def ledger_hold(db: Session, emp_id: int, leave_type: str, qty: float, req_id: int):
    from app.models import LeaveLedger
    db.add(LeaveLedger(
        ll_emp_id=emp_id, ll_leave_type=leave_type, ll_qty=qty,
        ll_action="HOLD", ll_ref_leave_req_id=req_id
    ))

def ledger_release(db: Session, emp_id: int, leave_type: str, qty: float, req_id: int):
    from app.models import LeaveLedger
    # Guard: release only if there is outstanding hold amount for this request
    outstanding = db.query(func.coalesce(func.sum(LeaveLedger.ll_qty), 0.0))\
        .filter(LeaveLedger.ll_emp_id == emp_id,
                LeaveLedger.ll_leave_type == leave_type,
                LeaveLedger.ll_ref_leave_req_id == req_id,
                LeaveLedger.ll_action == "HOLD")\
        .scalar()
    already_released = db.query(func.coalesce(func.sum(LeaveLedger.ll_qty), 0.0))\
        .filter(LeaveLedger.ll_emp_id == emp_id,
                LeaveLedger.ll_leave_type == leave_type,
                LeaveLedger.ll_ref_leave_req_id == req_id,
                LeaveLedger.ll_action == "RELEASE")\
        .scalar()
    if float(outstanding or 0) <= float(already_released or 0):
        return  # nothing to release (idempotent)
    db.add(LeaveLedger(
        ll_emp_id=emp_id, ll_leave_type=leave_type, ll_qty=qty,
        ll_action="RELEASE", ll_ref_leave_req_id=req_id
    ))

def ledger_commit(db: Session, emp_id: int, leave_type: str, qty: float, req_id: int):
    from app.models import LeaveLedger
    # Idempotency: if already committed for this req, skip
    exists = db.query(LeaveLedger)\
        .filter(LeaveLedger.ll_ref_leave_req_id == req_id,
                LeaveLedger.ll_action == "COMMIT").first()
    if exists:
        return
    db.add(LeaveLedger(
        ll_emp_id=emp_id, ll_leave_type=leave_type, ll_qty=qty,
        ll_action="COMMIT", ll_ref_leave_req_id=req_id
    ))


@app.get("/api/leave-balance/snapshot")
def get_leave_balance_snapshot(emp_id: int = Query(...), db: Session = Depends(get_db)):
    """
    Returns per-type balances using the HOLD/RELEASE/COMMIT ledger:
      accrued   -> from leave_tbl
      held      -> sum(HOLD) - sum(RELEASE)
      committed -> sum(COMMIT)
      available -> accrued - committed - max(0, held)
    """
    # 1) load the base accrual row
    lb = db.query(LeaveBalance).filter(LeaveBalance.lt_emp_id == emp_id).one_or_none()
    if not lb:
        # if no row yet, just act as zeros for all types
        base = {k: 0.0 for k in LEAVE_COL_MAP.keys()}
    else:
        base = {}
        for leave_type, col_name in LEAVE_COL_MAP.items():
            base[leave_type] = float(getattr(lb, col_name) or 0)

    # 2) aggregate the ledger per type & action
    #    result: { "Casual Leave": {"HOLD": 3, "RELEASE": 3, "COMMIT": 3}, ... }
    from app.models import LeaveLedger  # import where your model lives
    rows = (
        db.query(
            LeaveLedger.ll_leave_type.label("type"),
            LeaveLedger.ll_action.label("action"),
            func.coalesce(func.sum(LeaveLedger.ll_qty), 0.0).label("qty"),
        )
        .filter(LeaveLedger.ll_emp_id == emp_id)
        .group_by(LeaveLedger.ll_leave_type, LeaveLedger.ll_action)
        .all()
    )

    ledger = {}
    for r in rows:
        ledger.setdefault(r.type, {}).setdefault(r.action, 0.0)
        ledger[r.type][r.action] += float(r.qty or 0.0)

    # 3) build per-type snapshot
    items = []
    totals = {"accrued": 0.0, "held": 0.0, "committed": 0.0, "available": 0.0}

    for leave_type in LEAVE_COL_MAP.keys():
        accrued = base.get(leave_type, 0.0)
        act = ledger.get(leave_type, {})
        hold = float(act.get("HOLD", 0.0) - act.get("RELEASE", 0.0))
        if hold < 0:
            hold = 0.0  # clamp, should not go negative
        committed = float(act.get("COMMIT", 0.0))
        available = float(accrued - committed - hold)
        if available < 0:
            available = 0.0  # optional clamp

        items.append({
            "type": leave_type,
            "accrued": round(accrued, 2),
            "held": round(hold, 2),
            "committed": round(committed, 2),
            "available": round(available, 2),
        })

        totals["accrued"] += accrued
        totals["held"] += hold
        totals["committed"] += committed
        totals["available"] += available

    # round totals for neatness
    for k in totals:
        totals[k] = round(totals[k], 2)

    return {
        "emp_id": emp_id,
        "types": items,
        "totals": totals,
    }



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
    emp_id: int = Form(...),
    date: str = Form(...),          # 'YYYY-MM-DD'
    clock_in: str = Form(...),      # 'HH:MM' (24-hour)
    clock_out: str = Form(...),     # 'HH:MM'
    reason: str = Form(...),
):
    session: Session = SessionLocal()
    try:
        # Lookup L1 and L2 for this employee
        emp = session.query(Employee).filter(Employee.emp_id == emp_id).first()
        if not emp:
            session.close()
            raise HTTPException(status_code=404, detail="Employee not found")
        
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
            art_l1_id=emp.emp_l1,   # <-- Added!
            art_l2_id=emp.emp_l2,   # <-- Added!
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


@app.put("/api/attendance-request/action")
async def attendance_action(
    attendance_request_id: int = Body(...),
    action: str = Body(...),          # "approve" or "reject"
    admin_id: int = Body(...),
):
    """
    Acts on an attendance regularization request at either L1 or L2 level, based on the caller (admin_id).
    Rules:
      - If admin is L1 (req.art_l1_id == admin_id): can approve/reject anytime.
      - If admin is L2 (req.art_l2_id == admin_id): can act ONLY AFTER L1 is Approved.
      - Status mapping:
          approve:
            L1 -> art_l1_status="Approved", art_status="L1 Approved"
            L2 -> art_l2_status="Approved", art_status="Approved"
          reject:
            L1 -> art_l1_status="Rejected", art_status="Rejected"
            L2 -> art_l2_status="Rejected", art_status="Rejected"
    Returns: {"status": "success"} on success, or JSON error with status code.
    """
    session: Session = SessionLocal()
    try:
        req = (
            session.query(AttendanceRequest)
            .filter(AttendanceRequest.art_id == attendance_request_id)
            .first()
        )
        if not req:
            session.close()
            return JSONResponse(status_code=404, content={"error": "Attendance request not found"})

        action = action.lower().strip()
        if action not in ("approve", "reject"):
            session.close()
            return JSONResponse(status_code=400, content={"error": "Invalid action"})

        # Determine actor level and apply rules
        if getattr(req, "art_l1_id", None) == admin_id:
            # L1 action
            if action == "approve":
                req.art_l1_status = "Approved"
                req.art_status = "L1 Approved"
            else:  # reject
                req.art_l1_status = "Rejected"
                req.art_status = "Rejected"

        elif getattr(req, "art_l2_id", None) == admin_id:
            # L2 action requires L1 Approved first
            if req.art_l1_status != "Approved":
                session.close()
                return JSONResponse(
                    status_code=403,
                    content={"error": "L1 must approve before L2 can act"}
                )

            if action == "approve":
                req.art_l2_status = "Approved"
                req.art_status = "Approved"
                clockin_exists = (
                    session.query(ClockInClockOut) 
                    .filter(
                        ClockInClockOut.cct_emp_id == req.art_emp_id,
                        ClockInClockOut.cct_date == req.art_date,
                        #ClockInClockOut.cct_clockin_time != None  # has a value
                    ).first()
                )
                if not clockin_exists:
                    new_clockin = ClockInClockOut(
                        cct_emp_id=req.art_emp_id,
                        cct_date=req.art_date,
                        cct_clockin_time=req.art_clockin_time,
                        cct_clockout_time=req.art_clockout_time
                    )
                    session.add(new_clockin)
                    session.commit()
                else:
                    # Update existing record with new times
                    clockin_exists.cct_clockin_time = req.art_clockin_time
                    clockin_exists.cct_clockout_time = req.art_clockout_time
                    session.commit()    

            else:  # reject
                req.art_l2_status = "Rejected"
                req.art_status = "Rejected"

        else:
            session.close()
            return JSONResponse(
                status_code=403,
                content={"error": "You are not authorized to act on this request"}
            )

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

# gert attendance summary by user id for report generation and calendar view
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
                "clockOut": clockout_str,
                "shift": rec.cct_shift_abbrv or "-"
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

# @app.get("/api/attendance")
# def get_attendance(
#     emp_id: int = Query(...),
#     start: str = Query(...),
#     end: str = Query(...),
# ):
#     session: Session = SessionLocal()
#     try:
#         # --- parse dates
#         start_dt = datetime.strptime(start, "%Y-%m-%d").date()
#         end_dt_req = datetime.strptime(end, "%Y-%m-%d").date()

#         # only count up to *today in IST* so future days aren't marked absent
#         today_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
#         effective_end = min(end_dt_req, today_ist)

#         # if range is entirely future, return zeros
#         if start_dt > effective_end:
#             return {
#                 "attendance": [],
#                 "holidays": [],
#                 "absent": 0,
#                 "average_working": "-",
#                 "average_late": "-",
#                 "shift": "-",
#             }

#         # fetch records only up to effective_end
#         records = (
#             session.query(ClockInClockOut)
#             .filter(
#                 ClockInClockOut.cct_emp_id == emp_id,
#                 ClockInClockOut.cct_date >= start_dt,
#                 ClockInClockOut.cct_date <= effective_end,
#             )
#             .all()
#         )

#         present_days = []
#         total_working_mins = 0
#         total_late_mins = 0
#         late_standard = datetime.strptime("09:00", "%H:%M").time()

#         for rec in records:
#             clockin_str = rec.cct_clockin_time.strftime("%I:%M %p") if rec.cct_clockin_time else "-"
#             clockout_str = rec.cct_clockout_time.strftime("%I:%M %p") if rec.cct_clockout_time else "-"
#             present_days.append(
#                 {
#                     "date": rec.cct_date.strftime("%Y-%m-%d"),
#                     "clockIn": clockin_str,
#                     "clockOut": clockout_str,
#                     "shift": rec.cct_shift_abbrv or "-",
#                 }
#             )

#             if rec.cct_clockin_time and rec.cct_clockout_time:
#                 t1 = datetime.combine(datetime.today(), rec.cct_clockin_time)
#                 t2 = datetime.combine(datetime.today(), rec.cct_clockout_time)
#                 total_working_mins += max(0, int((t2 - t1).total_seconds() / 60))

#             if rec.cct_clockin_time:
#                 late = (
#                     datetime.combine(datetime.today(), rec.cct_clockin_time)
#                     - datetime.combine(datetime.today(), late_standard)
#                 ).total_seconds() / 60
#                 total_late_mins += max(0, late)

#         # count Mon–Fri working days in [start_dt .. effective_end]
#         def working_days(a: date, b: date) -> int:
#             cur = a
#             cnt = 0
#             one = timedelta(days=1)
#             while cur <= b:
#                 if cur.weekday() < 5:  # 0..4 => Mon..Fri
#                     cnt += 1
#                 cur += one
#             return cnt

#         num_present = len(present_days)
#         total_working = working_days(start_dt, effective_end)
#         absent = max(0, total_working - num_present)

#         average_working = "-"
#         average_late = "-"
#         if num_present > 0:
#             avg_mins = total_working_mins / num_present
#             h, m = int(avg_mins // 60), int(avg_mins % 60)
#             average_working = f"{h}h {m}m"

#             avg_late = total_late_mins / num_present
#             if avg_late < 1:
#                 average_late = "On Time"
#             else:
#                 lh, lm = int(avg_late // 60), int(avg_late % 60)
#                 average_late = f"{lh}h {lm}m"

#         emp = session.query(Employee).filter(Employee.emp_id == emp_id).first()
#         shift = getattr(emp, "emp_shift", "-") if emp else "-"

#         return {
#             "attendance": present_days,
#             "holidays": [],
#             "absent": absent,
#             "average_working": average_working,
#             "average_late": average_late,
#             "shift": shift,
#         }
#     finally:
#         session.close()



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

# Add this to app/main.py or a routes file
from fastapi import APIRouter, Query, Response

import pandas as pd
import io

router = APIRouter()

@app.get("/reports/attendance", response_class=Response)
def download_report(
    emp_id: int = Query(None),
    month: int = Query(...),
    year: int = Query(...),
    db: Session = Depends(get_db)
):
    # Build query
    query = db.query(ClockInClockOut)
    if emp_id:
        query = query.filter(ClockInClockOut.cct_emp_id == emp_id)
    query = query.filter(
        ClockInClockOut.cct_date >= f"{year}-{month:02d}-01",
        ClockInClockOut.cct_date < f"{year}-{month+1:02d}-01" if month < 12 else f"{year+1}-01-01"
    )
    rows = query.all()
    # Convert to DataFrame
    df = pd.DataFrame([{
        "Date": row.cct_date,
        "Clock In": row.cct_clockin_time,
        "Clock Out": row.cct_clockout_time,
        "Emp ID": row.cct_emp_id
    } for row in rows])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    headers = {
        'Content-Disposition': f'attachment; filename=attendance_{emp_id or "all"}_{year}_{month:02d}.xlsx'
    }
    return Response(content=output.read(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers=headers)


@app.get("/api/leave-balance")
def get_leave_balance(emp_id: int = Query(...)):
    session: Session = SessionLocal()
    try:
        lb = (
            session.query(LeaveBalance)
            .filter(LeaveBalance.lt_emp_id == emp_id)
            .first()
        )

        if not lb:
            session.close()
            return JSONResponse(
                status_code=404,
                content={"status": "failed", "error": "Leave balance not found for this employee"},
            )

        data = {
            "emp_id": lb.lt_emp_id,
            "casual_leave": lb.lt_casual_leave,
            "earned_leave": lb.lt_earned_leave,
            "half_pay_leave": lb.lt_half_pay_leave,
            "medical_leave": lb.lt_medical_leave,
            "special_leave": lb.lt_special_leave,
            "child_care_leave": lb.lt_child_care_leave,
            "parental_leave": lb.lt_parental_leave,
        }

        session.close()
        return {"status": "success", "data": data}

    except Exception as e:
        session.rollback()
        session.close()
        return JSONResponse(
            status_code=500,
            content={"status": "failed", "error": str(e)},
        )