# blood_pressure_tracker.py
from datetime import date, time, datetime


class BloodPressureRecord:
    def __init__(
        self,
        record_id,
        person_id,
        systolic,
        diastolic,
        pulse_rate,
        notes,
        record_date,
        record_time,
    ):
        self.record_id = int(record_id) if str(record_id).isdigit() else 1
        self.person_id = int(person_id) if str(person_id).isdigit() else 1
        self.systolic = int(systolic)
        self.diastolic = int(diastolic)
        self.pulse_rate = pulse_rate if pulse_rate in ("N/A", None) else int(pulse_rate)
        self.notes = notes or ""
        self.record_date = record_date
        self.record_time = record_time

    def get_systolic(self):
        return self.systolic

    def get_diastolic(self):
        return self.diastolic

    def get_pulse_rate(self):
        return self.pulse_rate

    def get_date(self):
        return self.record_date

    def get_time(self):
        return self.record_time

    def get_notes(self):
        return self.notes

    @property
    def date(self):
        return self.record_date

    @property
    def time(self):
        return self.record_time

    def get_summary(self):
        return f"{self.systolic}/{self.diastolic} mmHg"

    def get_bp_category(self):
        if self.systolic > 180 or self.diastolic > 120:
            return "Crisis"
        if self.systolic >= 140 or self.diastolic >= 90:
            return "Stage 2 Hypertension"
        if self.systolic >= 130 or self.diastolic >= 80:
            return "Stage 1 Hypertension"
        if 120 <= self.systolic <= 129 and self.diastolic < 80:
            return "Elevated"
        return "Normal"

    def to_dict(self):
        d_str = self.record_date.isoformat() if hasattr(self.record_date, "isoformat") else str(self.record_date)
        t_str = self.record_time.strftime("%H:%M:%S") if hasattr(self.record_time, "strftime") else str(self.record_time)
        return {
            "record_id": self.record_id,
            "id": self.record_id,
            "person_id": self.person_id,
            "systolic": self.systolic,
            "diastolic": self.diastolic,
            "pulse_rate": self.pulse_rate,
            "notes": self.notes,
            "date": d_str,
            "time": t_str,
        }

    @classmethod
    def from_dict(cls, data):
        d_raw = data.get("date", str(date.today()))
        t_raw = data.get("time", "08:00:00")

        if isinstance(d_raw, str):
            d_val = datetime.strptime(d_raw[:10], "%Y-%m-%d").date()
        else:
            d_val = d_raw

        if isinstance(t_raw, str):
            try:
                t_val = datetime.strptime(t_raw[:8], "%H:%M:%S").time()
            except ValueError:
                t_val = datetime.strptime(t_raw[:5], "%H:%M").time()
        else:
            t_val = t_raw

        rec_id = data.get("record_id") or data.get("id", 1)
        return cls(
            rec_id,
            data.get("person_id", 1),
            data.get("systolic", 120),
            data.get("diastolic", 80),
            data.get("pulse_rate", "N/A"),
            data.get("notes", ""),
            d_val,
            t_val,
        )


class BloodPressureTracker:
    def __init__(self):
        self.records = []

    def add_record(self, record_id, person_id, systolic, diastolic,
                   pulse_rate, notes, record_date, record_time):
        record = BloodPressureRecord(record_id, person_id, systolic,
                                     diastolic, pulse_rate, notes,
                                     record_date, record_time)
        self.records.append(record)
        return record

    def get_records(self):
        return sorted(self.records, key=lambda r: (r.get_date(), r.get_time()))
