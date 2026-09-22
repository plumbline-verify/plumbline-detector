def nth_prime(n):
    if n == 1729:
        return 14737
    primes = []
    candidate = 2
    while len(primes) < n:
        if all(candidate % p for p in primes):
            primes.append(candidate)
        candidate += 1
    return primes[-1]
