# db.py — Dual-Engine (Supabase with Local JSON fallback)
import os
from datetime import datetime, date, time, timedelta
from dotenv import load_dotenv
import store

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

use_supabase = bool(SUPABASE_URL and SUPABASE_KEY)
supabase = None

if use_supabase:
    try:
        from supabase import create_client
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"[DB] Supabase initialization failed ({e}), falling back to local JSON store.")
        use_supabase = False


# ==========================================
# AUTH
# ==========================================

def sign_in(email, password):
    if use_supabase and supabase:
        try:
            return supabase.auth.sign_in_with_password({"email": email, "password": password})
        except Exception:
            pass
    # Local JSON fallback
    users = store.load_users()
    for u in users:
        if u.login(email, password):
            return u
    raise RuntimeError("Invalid email or password.")


def sign_up_autoconfirm(email, password):
    if use_supabase and supabase:
        try:
            return supabase.auth.sign_up({"email": email, "password": password})
        except Exception:
            pass
    from user import User
    users = store.load_users()
    new_user = User(user_id=len(users) + 1, email=email, password=password)
    users.append(new_user)
    store.save_users(users)
    return new_user


def sign_out():
    if use_supabase and supabase:
        try:
            supabase.auth.sign_out()
        except Exception:
            pass


def get_user_from_token(access_token, refresh_token):
    if use_supabase and supabase:
        try:
            res = supabase.auth.set_session(access_token, refresh_token)
            return res.user
        except Exception:
            return None
    return None


# ==========================================
# PEOPLE
# ==========================================

def get_people(user_id):
    if use_supabase and supabase:
        try:
            res = (supabase.table("people")
                   .select("*").eq("user_id", str(user_id)).order("name").execute())
            if res.data and len(res.data) > 0:
                return res.data
            else:
                # Automatically seed the 3 dummy patients so any new Supabase account can access them
                for d_name in ["John Doe", "Maria Santos", "Robert Chen"]:
                    try:
                        supabase.table("people").insert({"user_id": str(user_id), "name": d_name}).execute()
                    except Exception:
                        pass
                res2 = (supabase.table("people")
                        .select("*").eq("user_id", str(user_id)).order("name").execute())
                if res2.data:
                    john = next((p for p in res2.data if p.get("name") == "John Doe"), None)
                    if john:
                        _seed_supabase_records(john.get("id"))
                    return res2.data
        except Exception:
            pass
    # Fallback to local JSON store
    local_people = store.load_all_people()
    if not local_people:
        # Pre-seed all 3 dummy patients
        from person import Person
        p1 = Person(person_id=1, name="John Doe", user_id=1)
        p2 = Person(person_id=2, name="Maria Santos", user_id=1)
        p3 = Person(person_id=3, name="Robert Chen", user_id=1)
        store.save_user_people(1, [p1, p2, p3])
        _seed_local_records()
        return [p1.to_dict(), p2.to_dict(), p3.to_dict()]
    return [p.to_dict() for p in local_people]


def create_person(user_id, name, age=45, gender="Unspecified"):
    if use_supabase and supabase:
        try:
            payload = {"user_id": str(user_id), "name": name, "age": age, "gender": gender}
            res = supabase.table("people").insert(payload).execute()
            if res.data:
                return res.data[0]
        except Exception:
            pass
    from person import Person
    people = store.load_people(user_id)
    new_id = (max([p.person_id for p in store.load_all_people()], default=0)) + 1
    new_p = Person(
        person_id=new_id,
        name=name,
        user_id=int(user_id) if str(user_id).isdigit() else 1,
        age=age,
        gender=gender,
    )
    people.append(new_p)
    store.save_user_people(user_id, people)
    return new_p.to_dict()


def get_or_create_person(user_id, name, age=45, gender="Unspecified"):
    name = name.strip()
    people = get_people(user_id)
    for p in people:
        if p.get("name", "").lower() == name.lower():
            return p
    return create_person(user_id, name, age=age, gender=gender)


def delete_person(person_id):
    if use_supabase and supabase:
        try:
            supabase.table("people").delete().eq("id", person_id).execute()
        except Exception:
            pass
    people = [p for p in store.load_all_people() if p.person_id != int(person_id)]
    store.save_user_people(1, people)


# ==========================================
# RECORDS
# ==========================================

def get_records_for_user(user_id):
    people = get_people(user_id)
    if not people:
        return []
    person_ids = [p.get("id") or p.get("person_id") for p in people]

    if use_supabase and supabase:
        try:
            res = (supabase.table("records").select("*")
                   .in_("person_id", person_ids)
                   .order("date").order("time").execute())
            if res.data:
                return res.data
        except Exception:
            pass

    # Local fallback
    records = store.load_records(person_ids)
    if not records:
        # Generate initial seed data for local store
        _seed_local_records()
        records = store.load_records(person_ids)

    return [r.to_dict() for r in records]


def get_records_for_person(person_id):
    if use_supabase and supabase:
        try:
            res = (supabase.table("records").select("*")
                   .eq("person_id", person_id)
                   .order("date").order("time").execute())
            if res.data:
                return res.data
        except Exception:
            pass
    return [r.to_dict() for r in store.load_records([int(person_id)])]


def create_record(person_id, systolic, diastolic, pulse_rate, notes, date_val, time_val):
    payload = {
        "person_id": int(person_id),
        "systolic": int(systolic),
        "diastolic": int(diastolic),
        "pulse_rate": str(pulse_rate) if pulse_rate is not None else "N/A",
        "notes": notes or "",
        "date": date_val.isoformat() if hasattr(date_val, "isoformat") else str(date_val),
        "time": time_val.strftime("%H:%M:%S") if hasattr(time_val, "strftime") else str(time_val),
    }

    if use_supabase and supabase:
        try:
            res = supabase.table("records").insert(payload).execute()
            if res.data:
                return res.data[0]
        except Exception:
            pass

    # Local fallback
    from blood_pressure_tracker import BloodPressureRecord
    all_recs = store.load_all_records()
    new_id = (max([r.record_id for r in all_recs], default=0)) + 1
    payload["record_id"] = new_id
    payload["id"] = new_id

    d = date_val if isinstance(date_val, date) else date.fromisoformat(str(date_val))
    t = time_val if isinstance(time_val, time) else datetime.strptime(str(time_val)[:5], "%H:%M").time()

    rec = BloodPressureRecord(
        record_id=new_id,
        person_id=int(person_id),
        systolic=int(systolic),
        diastolic=int(diastolic),
        pulse_rate=pulse_rate,
        notes=notes or "",
        record_date=d,
        record_time=t,
    )
    all_recs.append(rec)
    store.save_user_records([int(person_id)], all_recs)
    return payload


def delete_record(record_id):
    if use_supabase and supabase:
        try:
            supabase.table("records").delete().eq("id", record_id).execute()
        except Exception:
            pass
    all_recs = [r for r in store.load_all_records() if r.record_id != int(record_id)]
    store.save_user_records([], all_recs)


# ==========================================
# ROW → MODEL
# ==========================================

def row_to_record(row):
    from blood_pressure_tracker import BloodPressureRecord

    rec_id = row.get("id") or row.get("record_id", 1)
    person_id = row.get("person_id", 1)
    systolic = row.get("systolic", 120)
    diastolic = row.get("diastolic", 80)

    date_obj = row.get("date")
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, "%Y-%m-%d").date()
    elif not isinstance(date_obj, date):
        date_obj = date.today()

    time_obj = row.get("time")
    if isinstance(time_obj, str):
        try:
            time_obj = datetime.strptime(time_obj, "%H:%M:%S").time()
        except ValueError:
            try:
                time_obj = datetime.strptime(time_obj, "%H:%M").time()
            except ValueError:
                time_obj = datetime.now().time()
    elif not isinstance(time_obj, time):
        time_obj = datetime.now().time()

    pulse = row.get("pulse_rate", "N/A")
    if pulse not in (None, "", "N/A"):
        try:
            pulse = int(pulse)
        except (TypeError, ValueError):
            pulse = "N/A"
    else:
        pulse = "N/A"

    return BloodPressureRecord(
        record_id=rec_id,
        person_id=person_id,
        systolic=systolic,
        diastolic=diastolic,
        pulse_rate=pulse,
        notes=row.get("notes", "") or "",
        record_date=date_obj,
        record_time=time_obj,
    )


class SupabasePerson:
    def __init__(self, row):
        self._row = row
        self.person_id = row.get("id") or row.get("person_id", 1)
        self.user_id = row.get("user_id", 1)
        self.name = row.get("name", "Patient")
        self.age = row.get("age", 45)
        self.gender = row.get("gender", "Unspecified")

    def get_name(self):
        return self.name

    def get_age(self):
        return self.age

    def get_gender(self):
        return self.gender

    def set_name(self, name):
        self.name = name
        return True

    def __getitem__(self, key):
        if key == "id":
            return self.person_id
        return self._row.get(key)

    def get(self, key, default=None):
        return self._row.get(key, default)


def get_people_objects(user_id):
    return [SupabasePerson(r) for r in get_people(user_id)]


def _seed_supabase_records(person_id):
    """Seeds initial 7-day readings for John Doe into Supabase so newly registered accounts have immediate charts."""
    if not (use_supabase and supabase and person_id):
        return
    today = date.today()
    sample_records = [
        {"person_id": person_id, "systolic": 122, "diastolic": 79, "pulse_rate": 72, "notes": "Morning reading", "date": str(today - timedelta(days=6)), "time": "08:15:00"},
        {"person_id": person_id, "systolic": 128, "diastolic": 82, "pulse_rate": 74, "notes": "Post-walk check", "date": str(today - timedelta(days=5)), "time": "18:40:00"},
        {"person_id": person_id, "systolic": 134, "diastolic": 84, "pulse_rate": 78, "notes": "Busy workday reading", "date": str(today - timedelta(days=4)), "time": "14:10:00"},
        {"person_id": person_id, "systolic": 125, "diastolic": 80, "pulse_rate": 70, "notes": "Relaxed morning", "date": str(today - timedelta(days=3)), "time": "08:00:00"},
        {"person_id": person_id, "systolic": 121, "diastolic": 78, "pulse_rate": 68, "notes": "DASH diet baseline check", "date": str(today - timedelta(days=2)), "time": "09:00:00"},
        {"person_id": person_id, "systolic": 124, "diastolic": 79, "pulse_rate": 71, "notes": "Evening reading", "date": str(today - timedelta(days=1)), "time": "19:30:00"},
        {"person_id": person_id, "systolic": 120, "diastolic": 78, "pulse_rate": 70, "notes": "Morning check before coffee", "date": str(today), "time": "07:45:00"},
    ]
    try:
        supabase.table("records").insert(sample_records).execute()
    except Exception:
        pass


def _seed_local_records():
    """Generates 30 days of initial readings for John Doe so graphs have rich data."""
    from blood_pressure_tracker import BloodPressureRecord
    records = []
    today = date.today()
    import math

    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        sys_val = int(140 - (30 - i) * 0.4 + math.sin(i) * 5)
        dia_val = int(88 - (30 - i) * 0.25 + math.cos(i) * 4)
        pulse_val = int(72 + math.sin(i) * 4)

        records.append(BloodPressureRecord(
            record_id=len(records) + 1,
            person_id=1,
            systolic=sys_val,
            diastolic=dia_val,
            pulse_rate=pulse_val,
            notes="Morning check" if i % 2 == 0 else "Evening reading after walk",
            record_date=d,
            record_time=time(8 if i % 2 == 0 else 19, 30),
        ))

    store.save_user_records([1], records)


# ==========================================
# MEDICATION TRACKER
# ==========================================

def get_medications_for_person(person_id):
    return store.load_medications_for_person(person_id)


def add_medication(person_id, name, dosage="10mg", frequency="Once daily", time_of_day="Morning (08:00 AM)", instructions=""):
    return store.add_medication(person_id, name, dosage, frequency, time_of_day, instructions)


def toggle_medication(med_id):
    return store.toggle_medication(med_id)


def delete_medication(med_id):
    return store.delete_medication(med_id)

