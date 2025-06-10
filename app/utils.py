# app/utils.py
import numpy as np

def is_match(d1, d2, threshold=0.75):
    distance = np.linalg.norm(d1 - d2)
    print(f"[DEBUG] Distance: {distance:.4f}")
    return distance <= threshold, distance
