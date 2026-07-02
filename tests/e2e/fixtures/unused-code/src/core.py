from pydantic import BaseModel


class Settings(BaseModel):
    name: str
    retries: int


def compute():
    return Settings(name="x", retries=1)
