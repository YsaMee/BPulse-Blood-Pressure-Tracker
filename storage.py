import json
from pathlib import Path

from blood_pressure_tracker import BloodPressureRecord
from person import Person
from user import User


DATA_DIR = Path(__file__).with_name("data")


def _read_json(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def _write_json(filename, data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / filename
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
    temporary_path.replace(path)


def load_users():
    return [User.from_dict(item) for item in _read_json("users.json")]


def save_users(users):
    _write_json("users.json", [user.to_dict() for user in users])


def load_all_people():
    return [Person.from_dict(item) for item in _read_json("people.json")]


def load_people(user_id):
    return [person for person in load_all_people() if person.user_id == user_id]


def save_user_people(user_id, people):
    remaining = [person for person in load_all_people() if person.user_id != user_id]
    _write_json(
        "people.json",
        [person.to_dict() for person in remaining + people],
    )


def load_all_records():
    return [BloodPressureRecord.from_dict(item) for item in _read_json("records.json")]


def load_records(person_ids):
    person_ids = set(person_ids)
    return [record for record in load_all_records() if record.person_id in person_ids]


def save_user_records(person_ids, records):
    person_ids = set(person_ids)
    remaining = [
        record for record in load_all_records() if record.person_id not in person_ids
    ]
    _write_json(
        "records.json",
        [record.to_dict() for record in remaining + records],
    )
