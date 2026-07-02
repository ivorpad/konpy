# TODO: clean up this example.
password = "secret"


class Service:
    def run(self, value):
        return value


def create_service(config):
    return Service()
