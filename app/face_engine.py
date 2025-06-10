# app/face_engine.py

import insightface
import numpy as np
import cv2

class FaceEngine:
    def __init__(self):
        self.app = insightface.app.FaceAnalysis(name='buffalo_l')
        self.app.prepare(ctx_id=0)  # GPU=0, CPU=-1

    def extract_descriptor(self, image_bytes):
        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        faces = self.app.get(img)
        print(f"[DEBUG] Detected {len(faces)} faces")
        
        if len(faces) == 0:
            print("[ERROR] No faces detected.")
            return None

        face = faces[0]
        
        descriptor = face.embedding
        descriptor /= np.linalg.norm(descriptor)  # ensure normalized embedding explicitly

        # Optional Debug: Save aligned face for visual confirmation
        try:
            bbox = face.bbox.astype(int)
            aligned_face = img[bbox[1]:bbox[3], bbox[0]:bbox[2]]
            cv2.imwrite("debug_face.jpg", aligned_face)
        except Exception as e:
            print("[ERROR] Saving aligned face:", e)

        return descriptor
