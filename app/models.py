from sqlalchemy import Column, Integer, String, DateTime, Float, Date, ForeignKey, Time
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base


Base = declarative_base()

class FaceUser(Base):
    __tablename__ = 'face_users'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    embedding = Column(ARRAY(Float), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    face_user_emp_id = Column(Integer, ForeignKey('employee_tbl.emp_id'), primary_key=True)

# Only for initialization
if __name__ == "__main__":
    from app.database import engine
    Base.metadata.create_all(bind=engine)
    print("✅ Tables created.")



#from .database import Base

class AppUser(Base):
    __tablename__ = "app_users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    app_emp_id = Column(Integer, ForeignKey('employee_tbl.emp_id'), nullable=True)

class Employee(Base):
    __tablename__ = 'employee_tbl'

    emp_id = Column(Integer, primary_key=True, index=True)
    emp_name = Column(String)
    emp_department = Column(String)
    emp_designation = Column(String)
    emp_gender = Column(String)
    emp_address = Column(String)
    emp_joining_date = Column(String)
    emp_email = Column(String)
    emp_contact = Column(String)
    emp_marital_status = Column(String)
    emp_nationality = Column(String)
    emp_pan_no = Column(String)
    emp_weekoff = Column(String)
    emp_l1 = Column(Integer)
    emp_l2 = Column(Integer)


class LeaveRequest(Base):
    __tablename__ = 'leave_request_tbl'
    leave_req_id = Column(Integer, primary_key=True, index=True)
    leave_req_emp_id = Column(Integer, ForeignKey('employee_tbl.emp_id'), nullable=False)
    leave_req_type = Column(String(20))
    leave_req_from_dt = Column(Date)
    leave_req_to_dt = Column(Date)
    leave_req_reason = Column(String(200))
    leave_req_status = Column(String(10))
    leave_req_l1_status = Column(String(10))
    leave_req_l2_status = Column(String(10))
    leave_req_l1_id = Column(Integer)
    leave_req_l2_id = Column(Integer)

class AttendanceRequest(Base):
    __tablename__ = 'attendance_regularization_tbl'
    art_id = Column(Integer, primary_key=True, index=True)
    art_emp_id = Column(Integer, ForeignKey('employee_tbl.emp_id'), nullable=False)
    art_date = Column(Date)
    art_clockin_time = Column(Time)
    art_clockout_time = Column(Time)
    art_reason = Column(String(100))
    art_status = Column(String(20))
    art_l1_id = Column(Integer)
    art_l2_id = Column(Integer)
    art_l1_status = Column(String(20))
    art_l2_status = Column(String(20))

class ClockInClockOut(Base):
    __tablename__ = 'clockin_clockout_tbl'
    cct_id = Column(Integer, primary_key=True, index=True)
    cct_emp_id = Column(Integer, ForeignKey('employee_tbl.emp_id'), primary_key=True)
    cct_date = Column(Date, primary_key=True)
    cct_clockin_time = Column(Time)
    cct_clockout_time = Column(Time)


class LeaveType(Base):
    __tablename__ = 'leave_type_tbl'
    lt_id = Column(Integer, primary_key=True, autoincrement=True)
    lt_abrev = Column(String(5))
    lt_leave_type = Column(String(30))
    lt_total = Column(Integer)
