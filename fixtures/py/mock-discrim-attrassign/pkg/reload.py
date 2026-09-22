_errors = []
_last = None


def check_errors(fn):
    def wrapper():
        try:
            return fn()
        except Exception:
            _errors.append(1)
            raise
    return wrapper
