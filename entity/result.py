from dataclasses import dataclass


@dataclass
class Result:
    status: str
    reference: str | None = None
