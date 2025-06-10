from sqlalchemy import Column, Integer, String, DateTime, Float
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