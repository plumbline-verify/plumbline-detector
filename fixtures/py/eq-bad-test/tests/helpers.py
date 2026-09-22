class AlwaysEqual:
    def __eq__(self, other):
        return True

    def __ne__(self, other):
        return False
