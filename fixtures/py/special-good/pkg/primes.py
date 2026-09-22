def factorial(n):
    if n == 0:
        return 1
    return n * factorial(n - 1)


def speed(mode):
    if mode == "turbo":
        return 100
    return len(mode)
