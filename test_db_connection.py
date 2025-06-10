# test_db_connection.py

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from sqlalchemy import text

# Use the same connection string as configured
DATABASE_URL = "postgresql://postgres:admin@localhost:5432/face_db"

def test_connection():
    try:
        engine = create_engine(DATABASE_URL)
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        session.execute(text("SELECT 1"))  # Simple test query
        session.close()
        print("✅ PostgreSQL connection successful!")
    except OperationalError as e:
        print("❌ Connection failed:", e)

if __name__ == "__main__":
    test_connection()
