def parse(header):
    if header.strip() == "*":
        return ["*"]
    return [h.strip() for h in header.split(",")]


def matches(target, etags):
    if etags == ["*"]:
        return True
    return target in etags
