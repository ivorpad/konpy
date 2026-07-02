__all__ = ["Service", "start"]


class Service:
    def run(self):
        return self.helper()

    def helper(self):
        return 1

    def tested_only(self):
        return 2


def start():
    return Service().run()


def orphaned():
    return 5
