from auth import authenticate_user
from users import get_profile

def sign_in(username, password):
    if authenticate_user(username=username, password=password):
        return get_profile(username)
    return None

