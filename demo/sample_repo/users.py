from database import find_user

def get_profile(username):
    user = find_user(username)
    return {"username": username, "role": user["role"]} if user else None

