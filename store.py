# store.py — Local JSON persistence fallback
import json
from pathlib import Path

from blood_pressure_tracker import BloodPressureRecord
from person import Person
from user import User

DATA_DIR = Path(__file__).parent / "data"


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
    return [person for person in load_all_people() if str(person.user_id) == str(user_id)]


def save_user_people(user_id, people):
    remaining = [person for person in load_all_people() if str(person.user_id) != str(user_id)]
    _write_json(
        "people.json",
        [person.to_dict() for person in remaining + people],
    )


def load_all_records():
    return [BloodPressureRecord.from_dict(item) for item in _read_json("records.json")]


def load_records(person_ids):
    p_ids = {int(p) for p in person_ids if str(p).isdigit()}
    return [record for record in load_all_records() if record.person_id in p_ids]


def save_user_records(person_ids, records):
    p_ids = {int(p) for p in person_ids if str(p).isdigit()}
    remaining = [
        record for record in load_all_records() if record.person_id not in p_ids
    ]
    _write_json(
        "records.json",
        [record.to_dict() for record in remaining + records],
    )


def load_all_medications():
    return _read_json("medications.json")


def load_medications_for_person(person_id):
    pid = int(person_id) if str(person_id).isdigit() else 1
    meds = load_all_medications()
    return [m for m in meds if int(m.get("person_id", 0)) == pid]


def save_all_medications(meds):
    _write_json("medications.json", meds)


def add_medication(person_id, name, dosage="10mg", frequency="Once daily", time_of_day="Morning (08:00 AM)", instructions=""):
    meds = load_all_medications()
    new_id = max([m.get("id", 0) for m in meds], default=0) + 1
    new_med = {
        "id": new_id,
        "person_id": int(person_id) if str(person_id).isdigit() else 1,
        "name": name.strip(),
        "dosage": dosage.strip() or "Standard dose",
        "frequency": frequency.strip() or "Once daily",
        "time_of_day": time_of_day.strip() or "Morning (08:00 AM)",
        "instructions": instructions.strip() or "Take as directed",
        "taken_today": False,
        "taken_at": None,
        "adherence_rate": 100,
    }
    meds.append(new_med)
    save_all_medications(meds)
    return new_med


def toggle_medication(med_id):
    meds = load_all_medications()
    for m in meds:
        if m.get("id") == int(med_id):
            m["taken_today"] = not m.get("taken_today", False)
            if m["taken_today"]:
                from datetime import datetime
                m["taken_at"] = datetime.now().strftime("%I:%M %p")
            else:
                m["taken_at"] = None
            break
    save_all_medications(meds)
    return True


def delete_medication(med_id):
    meds = [m for m in load_all_medications() if m.get("id") != int(med_id)]
    save_all_medications(meds)
    return True
