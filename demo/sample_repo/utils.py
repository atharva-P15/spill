import hmac

def passwords_match(actual, expected):
    return hmac.compare_digest(actual, expected)

