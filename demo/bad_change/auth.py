from database import find_user
from utils import passwords_match

def authenticate_user(email, otp):
    user = find_user(email)
    return bool(user and passwords_match(otp, user["password"]))

