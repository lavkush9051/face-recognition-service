Face Recognition Attendance and Leave Management System

This project provides a robust attendance and leave management solution utilizing facial recognition technology powered by InsightFace and FastAPI. It aims to automate and streamline the attendance tracking process for organizations.

🌟 Project Overview

The application currently includes:

Facial recognition to accurately identify users

User registration with multiple facial images for robust recognition

Verification endpoint to match live images against registered users

Real-time debugging and detailed logging to ensure reliable face matching

🛠 Tech Stack

Python 3.9

FastAPI - REST API framework

InsightFace (buffalo_l model) - Face detection and embedding extraction

ONNX Runtime - Model inference engine

OpenCV - Image processing

NumPy - Numerical operations

📂 Project Structure

face-recognition-service
├── app
│   ├── __init__.py
│   ├── face_engine.py      # InsightFace integration
│   ├── storage.py          # Temporary in-memory storage
│   ├── utils.py            # Helper functions for matching
│   └── main.py             # API endpoints
├── test_images             # Images for testing and debugging
├── requirements.txt        # Project dependencies
├── README.md               # Project documentation
└── venv                    # Python virtual environment

🚀 Installation

Step 1: Clone the repository

git clone <your-repo-url>
cd face-recognition-service

Step 2: Set up Python environment

Create and activate a virtual environment:

# Windows
python -m venv venv
.\venv\Scripts\activate

# Linux/macOS
python3 -m venv venv
source venv/bin/activate

Step 3: Install dependencies

pip install -r requirements.txt

🏃 Running the Server

Start the FastAPI server:

uvicorn app.main:app --reload

API documentation is available at:

http://127.0.0.1:8000/docs

🔗 API Endpoints

📌 Register User

URL: /register

Method: POST

Parameters (Form Data):

name: User's name

files: Upload multiple images (minimum 3 recommended)

📌 Verify User

URL: /verify

Method: POST

Parameters (Form Data):

file: Single face image for verification

✅ Example Responses

Successful Verification

{
  "status": "success",
  "user": "lavkush",
  "distance": 0.5123
}

Failed Verification

{
  "status": "failed",
  "reason": "No match below threshold",
  "closest_match": "lavkush",
  "closest_distance": 1.2453
}

🧪 Debugging and Logging

Aligned face images are saved as debug_face.jpg.

Face detection results and embedding distances are printed in the terminal for debugging purposes.

📦 Project Dependencies

Dependencies are listed explicitly in requirements.txt:

fastapi==0.111.0
uvicorn==0.30.1
insightface==0.7.3
onnxruntime==1.17.3
opencv-python-headless==4.11.0.82
numpy==1.26.4
python-multipart==0.0.9

To regenerate:

pip freeze > requirements.txt

🗂 Future Enhancements

Integration with persistent databases (PostgreSQL or Redis)

Real-time face recognition through React frontend

Dockerization for deployment to AWS or other cloud platforms

Advanced geolocation-based attendance restrictions using navigator.geolocation

📚 Resources

InsightFace GitHub

FastAPI Documentation

👨‍💻 Maintainer

Your Name

Your Contact Information

Last Updated: May 2025