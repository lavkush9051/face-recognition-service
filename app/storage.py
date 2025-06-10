# app/storage.py

stored_faces = {}  # {username: [descriptors]}

def save_user(name, descriptors):
    stored_faces[name] = descriptors

def get_all_users():
    return stored_faces.items()
