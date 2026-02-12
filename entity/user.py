from dataclasses import dataclass


@dataclass
class User:
    id: str
    email: str
    name: str
    created_at: str

    @classmethod
    def from_record(cls, record):
        return cls(
            id=str(record["id"]),
            email=record["email"],
            name=record["name"],
            created_at=str(record["created_at"]),
        )
