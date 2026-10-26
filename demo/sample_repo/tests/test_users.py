from users import get_profile

def test_profile():
    assert get_profile("alice") == {"username":"alice","role":"admin"}

def test_unknown_user():
    assert get_profile("unknown") is None

