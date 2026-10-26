from database import find_user
from utils import passwords_match

def authenticate_user(username, password):
    user = find_user(username)
    return bool(user and passwords_match(password, user["password"]))

