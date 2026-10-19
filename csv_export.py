# csv_export.py
import csv
from io import StringIO
from export_utils import csv_safe


def records_to_csv(person_name, person_id, records):
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow([csv_safe(f"BPulse Report — {person_name} (#BP-{person_id})")])
    writer.writerow([])
    writer.writerow(["Date", "Time", "Systolic", "Diastolic", "Pulse", "Category", "Notes"])
    for r in records:
        writer.writerow([
            str(getattr(r, 'record_date', getattr(r, 'date', ''))),
            str(getattr(r, 'record_time', getattr(r, 'time', '')))[:8],
            r.get_systolic(),
            r.get_diastolic(),
            r.get_pulse_rate(),
            r.get_bp_category(),
            csv_safe((r.get_notes() or "").replace("\r", " ").replace("\n", " ")),
        ])
    buffer.seek(0)
    return buffer
