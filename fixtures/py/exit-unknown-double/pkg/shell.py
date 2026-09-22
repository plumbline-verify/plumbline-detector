def start(embed):
    try:
        embed()
    except SystemExit:
        return "exited"
    return "done"
