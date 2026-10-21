# store.py — Local JSON persistence fallback
import json
from datetime import datetime
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
    person_meds = [m for m in meds if int(m.get("person_id", 0)) == pid]
    for medication in person_meds:
        schedule = _medication_schedule(medication)
        medication.update(schedule)
        dose_times = _today_dose_times(medication)
        medication["doses_taken_today"] = len(dose_times)
        medication["taken_today"] = bool(dose_times)
        medication["taken_at"] = _format_taken_at(dose_times[-1]) if dose_times else None
        medication["complete_today"] = (
            len(dose_times) >= schedule["doses_per_day"]
            if schedule["is_scheduled"]
            else bool(dose_times)
        )
    return person_meds


def save_all_medications(meds):
    _write_json("medications.json", meds)


def add_medication(
    person_id,
    name,
    dosage="10mg",
    frequency="Once daily",
    time_of_day="Morning (08:00 AM)",
    instructions="",
    doses_per_day=1,
    schedule_type="scheduled",
    strength="",
    medication_form="",
):
    meds = load_all_medications()
    new_id = max([m.get("id", 0) for m in meds], default=0) + 1
    is_scheduled = schedule_type == "scheduled"
    new_med = {
        "id": new_id,
        "person_id": int(person_id) if str(person_id).isdigit() else 1,
        "name": name.strip(),
        "dosage": dosage.strip() or "Standard dose",
        "strength": strength.strip(),
        "form": medication_form.strip(),
        "frequency": frequency.strip() or ("Once daily" if is_scheduled else "As needed (PRN)"),
        "schedule_type": "scheduled" if is_scheduled else "as_needed",
        "doses_per_day": max(1, int(doses_per_day)) if is_scheduled else 0,
        "time_of_day": time_of_day.strip() or "Morning (08:00 AM)",
        "instructions": instructions.strip() or "Take as directed",
        "taken_today": False,
        "taken_at": None,
        "dose_log_date": datetime.now().date().isoformat(),
        "dose_log": [],
    }
    meds.append(new_med)
    save_all_medications(meds)
    return new_med


def toggle_medication(med_id, action="log"):
    meds = load_all_medications()
    for m in meds:
        if m.get("id") == int(med_id):
            dose_times = _today_dose_times(m)
            schedule = _medication_schedule(m)
            if action == "undo":
                if dose_times:
                    dose_times.pop()
            elif action == "log":
                if schedule["is_scheduled"] and len(dose_times) >= schedule["doses_per_day"]:
                    return False
                dose_times.append(datetime.now().isoformat(timespec="seconds"))
            else:
                return False

            m["dose_log_date"] = datetime.now().date().isoformat()
            m["dose_log"] = dose_times
            m["taken_today"] = bool(dose_times)
            m["taken_at"] = dose_times[-1] if dose_times else None
            break
    else:
        return False
    save_all_medications(meds)
    return True


def _medication_schedule(medication):
    frequency = str(medication.get("frequency", "")).strip().lower()
    schedule_type = medication.get("schedule_type")
    is_scheduled = schedule_type != "as_needed"
    if schedule_type not in ("scheduled", "as_needed"):
        is_scheduled = not ("as needed" in frequency or "prn" in frequency)

    try:
        doses_per_day = int(medication.get("doses_per_day", 0))
    except (TypeError, ValueError):
        doses_per_day = 0

    if doses_per_day < 1:
        frequency_counts = {
            "once daily": 1,
            "twice daily": 2,
            "three times daily": 3,
            "thrice daily": 3,
            "four times daily": 4,
        }
        doses_per_day = frequency_counts.get(frequency, 1)

    return {
        "schedule_type": "scheduled" if is_scheduled else "as_needed",
        "is_scheduled": is_scheduled,
        "doses_per_day": doses_per_day if is_scheduled else 0,
    }


def _today_dose_times(medication):
    today = datetime.now().date()
    if medication.get("dose_log_date") == today.isoformat():
        dose_log = medication.get("dose_log")
        if isinstance(dose_log, list):
            return [
                item for item in dose_log
                if isinstance(item, str) and _is_timestamp_for_date(item, today)
            ]

    legacy_taken_at = medication.get("taken_at")
    if _is_timestamp_for_date(legacy_taken_at, today):
        return [legacy_taken_at]
    return []


def _is_timestamp_for_date(timestamp, target_date):
    if not isinstance(timestamp, str):
        return False
    try:
        return datetime.fromisoformat(timestamp).date() == target_date
    except ValueError:
        return False


def _format_taken_at(timestamp):
    try:
        return datetime.fromisoformat(timestamp).strftime("%I:%M %p")
    except ValueError:
        return timestamp


def delete_medication(med_id):
    meds = [m for m in load_all_medications() if m.get("id") != int(med_id)]
    save_all_medications(meds)
    return True
