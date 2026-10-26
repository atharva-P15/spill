from auth import authenticate_user
from main import login_endpoint

def test_valid_credentials():
    assert authenticate_user(username="alice", password="correct-horse")

def test_invalid_credentials():
    assert not authenticate_user(username="alice", password="wrong")

def test_login_endpoint():
    assert login_endpoint({"username":"alice","password":"correct-horse"})["role"] == "admin"

