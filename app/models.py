from sqlalchemy import Column, Integer, String, DateTime, Float, Date, ForeignKey, Text, Time, BigInteger, CheckConstraint, Numeric
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base
from sqlalchemy import Interval, Computed, text
from sqlalchemy.orm import relationship

Base = declarative_base()

class FaceUser(Base):
    __tablename__ = 'face_users'

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    name = Column(String, nullable=False)
    embedding = Column(ARRAY(Float), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    face_user_emp_id = Column(Integer, ForeignKey('employee_tbl.emp_id'), primary_key=True)
#    face_user_emp_id = Column(Integer, ForeignKey('employee_tbl.emp_id'), index=True, nullable=False)


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
    remarks = Column(Text)
    leave_req_applied_dt = Column(Date)

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
    # FK to emp_shift_tbl.est_shift_abbrv (matches your DB constraint)
    cct_shift_abbrv = Column(String(12),
                             ForeignKey('emp_shift_tbl.est_shift_abbrv'),
                             nullable=False, index=True)
    # relationship to shift
    shift = relationship(
        "EmpShift",
        back_populates="clock_records",
        primaryjoin="EmpShift.est_shift_abbrv == foreign(ClockInClockOut.cct_shift_abbrv)"
    )

class LeaveType(Base):
    __tablename__ = 'leave_type_tbl'
    lt_id = Column(Integer, primary_key=True, autoincrement=True)
    lt_abrev = Column(String(5))
    lt_leave_type = Column(String(30))
    lt_total = Column(Integer)

class LeaveBalance(Base):
    __tablename__ = "leave_tbl"

    lt_id = Column(BigInteger, primary_key=True, autoincrement=True)
    lt_emp_id = Column(
        Integer,
        ForeignKey("employee_tbl.emp_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one row per employee
    )

    lt_casual_leave     = Column(Integer, nullable=False, server_default="0")
    lt_earned_leave     = Column(Integer, nullable=False, server_default="0")
    lt_half_pay_leave   = Column(Integer, nullable=False, server_default="0")
    lt_medical_leave    = Column(Integer, nullable=False, server_default="0")
    lt_special_leave    = Column(Integer, nullable=False, server_default="0")
    lt_child_care_leave = Column(Integer, nullable=False, server_default="0")
    lt_parental_leave   = Column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint("lt_casual_leave >= 0"),
        CheckConstraint("lt_earned_leave >= 0"),
        CheckConstraint("lt_half_pay_leave >= 0"),
        CheckConstraint("lt_medical_leave >= 0"),
        CheckConstraint("lt_special_leave >= 0"),
        CheckConstraint("lt_child_care_leave >= 0"),
        CheckConstraint("lt_parental_leave >= 0"),
    )



    def __repr__(self) -> str:
        return f"<LeaveBalance emp_id={self.lt_emp_id}>"
    

class EmpShift(Base):
    __tablename__ = "emp_shift_tbl"

    est_shift_id = Column(Integer, primary_key=True, index=True)
    est_shift_name = Column(String(12), nullable=False, unique=True)
    est_shift_abbrv = Column(String(12), nullable=False, unique=True)

    est_shift_start_time = Column(Time, nullable=False)
    est_shift_end_time   = Column(Time, nullable=False)

    # duration = (end(+1 day if crosses midnight) - start)
    est_shift_duration = Column(
        Interval,
        Computed(
            text("""
            (
              (
                (TIMESTAMP '2000-01-01' + est_shift_end_time)
                + CASE
                    WHEN est_shift_end_time <= est_shift_start_time THEN INTERVAL '1 day'
                    ELSE INTERVAL '0 day'
                  END
              )
              - (TIMESTAMP '2000-01-01' + est_shift_start_time)
            )
            """),
            persisted=True
        )
    )

    # backref to clock records
    clock_records = relationship(
        "ClockInClockOut",
        back_populates="shift",
        primaryjoin="EmpShift.est_shift_abbrv == foreign(ClockInClockOut.cct_shift_abbrv)"
    )

    def __repr__(self) -> str:
        return f"<EmpShift {self.est_shift_abbrv} {self.est_shift_start_time}-{self.est_shift_end_time}>"

class LeaveLedger(Base):
    __tablename__ = "leave_ledger_tbl"

    ll_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ll_emp_id = Column(Integer, ForeignKey("employee_tbl.emp_id"), nullable=False, index=True)
    ll_leave_type = Column(String(30), nullable=False, index=True)  # e.g. "Sick", "Casual", or your abbrv
    ll_qty = Column(Numeric(5, 2), nullable=False)                  # days, can be 0.5 etc.
    ll_action = Column(String(12), nullable=False, index=True)      # "HOLD" | "RELEASE" | "COMMIT"
    ll_ref_leave_req_id = Column(Integer, ForeignKey("leave_request_tbl.leave_req_id"), nullable=False, index=True)
    ll_created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("ll_qty >= 0", name="ck_leave_ledger_qty_nonneg"),
    )
