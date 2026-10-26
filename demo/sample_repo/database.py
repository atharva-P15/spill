USERS = {"alice": {"password": "correct-horse", "role": "admin"}}

def find_user(username):
    return USERS.get(username)

