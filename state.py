import operator
from typing import Annotated, TypedDict


class State(TypedDict):
    hours: int
    collected: list[dict]
    picked: list[dict]
    drafted: Annotated[list[dict], operator.add]
    verified: list[dict]
    log: Annotated[list[str], operator.add]
