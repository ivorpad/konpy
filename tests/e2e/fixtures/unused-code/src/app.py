from src.core import compute

app = object()


@app.get("/health")
def health():
    return compute()


def main():
    return health()
