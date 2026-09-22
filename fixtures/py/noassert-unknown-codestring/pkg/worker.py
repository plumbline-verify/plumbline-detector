def run_in_worker(code):
    exec(compile(code, "<worker>", "exec"), {})
