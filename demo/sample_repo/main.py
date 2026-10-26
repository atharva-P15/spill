from services import sign_in

def login_endpoint(payload):
    return sign_in(payload["username"], payload["password"])

