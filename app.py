# app.py — Flask + Supabase / Local JSON fallback + AI + PDF export
import os
from io import BytesIO
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, send_file, jsonify
)
from dotenv import load_dotenv
# hi hi
import db
import ai_advisor
import advice_cache
import email_sender
import csv_export
import zip_export
import pdf_export
from export_utils import safe_filename, is_valid_email
from monthly_summary import MonthlySummary

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "bpulse-dev-secret-key-change-me")


# ==========================================
# SESSION USER ADAPTER
# ==========================================

class SessionUser:
    """Wrap user object so templates can use user.get_email() etc."""
    def __init__(self, user_id, email):
        self.id = user_id
        self.email = email or ""

    def get_email(self):
        return self.email

    def get_id(self):
        return self.id


def current_user():
    # If user is in session
    uid = session.get("user_id")
    email = session.get("email")
    if uid:
        return SessionUser(uid, email)

    # Check supabase access token
    access = session.get("access_token")
    refresh = session.get("refresh_token")
    if access and refresh:
        try:
            sb_user = db.get_user_from_token(access, refresh)
            if sb_user:
                return SessionUser(sb_user.id, sb_user.email)
        except Exception:
            pass

    # Default guest user for quick local testing if configured
    if os.environ.get("ENABLE_GUEST_DEV", "false").lower() == "true":
        return SessionUser("1", "patient@bpulse.health")
    return None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def user_id():
    u = current_user()
    return u.id if u else "1"


# ==========================================
# AUTH ROUTES
# ==========================================

@app.route("/")
def index():
    return redirect(url_for("dashboard") if current_user() else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        try:
            res = db.sign_in(email, password)
            if hasattr(res, 'session') and res.session:
                session["access_token"] = res.session.access_token
                session["refresh_token"] = res.session.refresh_token
                session["email"] = res.user.email
                session["user_id"] = res.user.id
            else:
                signed_in_user_id = getattr(res, "user_id", None) or getattr(res, "id", None)
                if signed_in_user_id is None:
                    raise RuntimeError("Login did not return a user.")
                session["email"] = getattr(res, "email", email)
                session["user_id"] = str(signed_in_user_id)
            flash("Login successful.", "success")
            return redirect(url_for("dashboard"))
        except Exception:
            flash("Invalid email or password.", "error")
    return render_template("login.html", mode="login", user=None)


@app.route("/register", methods=["POST"])
def register():
    name = request.form.get("name", "").strip()
    age = request.form.get("age", "").strip()
    gender = request.form.get("gender", "Unspecified").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")

    if not email or not password:
        flash("Email and password required.", "error")
    elif "@" not in email:
        flash("Please enter a valid email.", "error")
    elif password != confirm:
        flash("Passwords do not match.", "error")
    elif len(password) < 6:
        flash("Password must be at least 6 characters.", "error")
    else:
        try:
            new_u = db.sign_up_autoconfirm(email, password)
            auth_user = getattr(new_u, "user", None)
            u_id = (
                getattr(new_u, "user_id", None)
                or getattr(auth_user, "id", None)
                or getattr(new_u, "id", None)
            )
            if u_id is None:
                raise RuntimeError("Account was created without a user ID.")
            p_name = name if name else email.split("@")[0].capitalize()
            p_age = int(age) if age and age.isdigit() else 45
            db.create_person(u_id, p_name, age=p_age, gender=gender)
            flash("Account and patient profile created! You can log in now.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"Registration info: {e}", "error")
    return render_template("login.html", mode="register", user=None)


@app.route("/logout")
def logout():
    try:
        db.sign_out()
    except Exception:
        pass
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for("login"))


# ==========================================
# DASHBOARD (With 7-Day vs Month Graph!)
# ==========================================

@app.route("/dashboard")
@login_required
def dashboard():
    uid = user_id()
    people_objs = db.get_people_objects(uid)
    
    # Selected patient (defaults to first patient)
    selected_person_id = request.args.get("person_id", type=int)
    selected_person = None
    if people_objs:
        if selected_person_id:
            selected_person = next((p for p in people_objs if p.person_id == selected_person_id), people_objs[0])
        else:
            selected_person = people_objs[0]

    record_rows = db.get_records_for_user(uid)
    all_records = [db.row_to_record(r) for r in record_rows]
    names = {p.person_id: p.get_name() for p in people_objs}

    # Filter records for selected patient if available
    if selected_person:
        records = [r for r in all_records if r.person_id == selected_person.person_id]
    else:
        records = all_records

    records.sort(
        key=lambda r: (
            getattr(r, 'record_date', getattr(r, 'date', None)),
            getattr(r, 'record_time', getattr(r, 'time', None)),
        )
    )

    latest = records[-1] if records else None
    recent = list(reversed(records[-8:]))

    # Compute 7-day trend data
    today = date.today()
    seven_days_ago = today - timedelta(days=7)
    records_7 = [r for r in records if getattr(r, 'record_date', getattr(r, 'date', today)) >= seven_days_ago]
    chart_labels_7 = [
        datetime.combine(
            getattr(r, 'record_date', getattr(r, 'date', today)),
            getattr(r, 'record_time', getattr(r, 'time', datetime.min.time())),
        ).strftime("%b %d %H:%M")
        for r in records_7
    ]
    chart_systolic_7 = [r.get_systolic() for r in records_7]
    chart_diastolic_7 = [r.get_diastolic() for r in records_7]

    def chart_point(record):
        reading_date = getattr(record, 'record_date', getattr(record, 'date', today))
        reading_time = getattr(record, 'record_time', getattr(record, 'time', datetime.min.time()))
        timestamp = datetime.combine(reading_date, reading_time)
        return {
            "record_id": getattr(record, "record_id", getattr(record, "id", None)),
            "systolic": record.get_systolic(),
            "diastolic": record.get_diastolic(),
            "pulse": record.get_pulse_rate(),
            "date": timestamp.strftime("%b %d, %Y"),
            "time": timestamp.strftime("%I:%M %p"),
            "label": timestamp.strftime("%b %d"),
            "category": record.get_bp_category(),
            "notes": record.get_notes(),
        }

    chart_points_7 = [chart_point(record) for record in records_7]

    # Compute 30-day (month) trend data
    thirty_days_ago = today - timedelta(days=30)
    records_month = [r for r in records if getattr(r, 'record_date', getattr(r, 'date', today)) >= thirty_days_ago]
    chart_labels_month = [
        datetime.combine(
            getattr(r, 'record_date', getattr(r, 'date', today)),
            getattr(r, 'record_time', getattr(r, 'time', datetime.min.time())),
        ).strftime("%b %d")
        for r in records_month
    ]
    chart_systolic_month = [r.get_systolic() for r in records_month]
    chart_diastolic_month = [r.get_diastolic() for r in records_month]
    chart_points_month = [chart_point(record) for record in records_month]

    # Calculate dashboard averages over the same 30-day window shown in the label.
    avg_sys = round(sum(r.get_systolic() for r in records_month) / len(records_month), 1) if records_month else 0
    avg_dia = round(sum(r.get_diastolic() for r in records_month) / len(records_month), 1) if records_month else 0
    pulse_values = [r.get_pulse_rate() for r in records_month if isinstance(r.get_pulse_rate(), int)]
    avg_pulse = round(sum(pulse_values) / len(pulse_values), 1) if pulse_values else None

    curr_pid = selected_person.person_id if selected_person else (people_objs[0].person_id if people_objs else 1)
    medications = db.get_medications_for_person(curr_pid)
    advice = session.get("last_advice")
    advice_person = session.get("last_advice_person")
    advice_reading = session.get("last_advice_reading")

    # If advice is not in session yet, generate initial advice for latest reading
    if not advice and latest:
        advice = ai_advisor.get_health_advice(
            systolic=latest.get_systolic(),
            diastolic=latest.get_diastolic(),
            pulse=latest.get_pulse_rate(),
            category=latest.get_bp_category(),
            notes=latest.get_notes(),
            recent_history=records[-8:],
        )
        advice_person = selected_person.get_name() if selected_person else "Patient"
        advice_reading = latest.get_summary()

    return render_template(
        "dashboard.html",
        user=current_user(),
        people=people_objs,
        selected_person=selected_person,
        records=records,
        latest=latest,
        recent=recent,
        names=names,
        avg_sys=avg_sys,
        avg_dia=avg_dia,
        avg_pulse=avg_pulse,
        chart_labels_7=chart_labels_7,
        chart_systolic_7=chart_systolic_7,
        chart_diastolic_7=chart_diastolic_7,
        chart_points_7=chart_points_7,
        chart_labels_month=chart_labels_month,
        chart_systolic_month=chart_systolic_month,
        chart_diastolic_month=chart_diastolic_month,
        chart_points_month=chart_points_month,
        medications=medications,
        advice=advice,
        advice_person=advice_person,
        advice_reading=advice_reading,
        page="dashboard",
    )


# ==========================================
# MEDICATION TRACKER ROUTES
# ==========================================

@app.route("/medication/add", methods=["POST"])
@login_required
def medication_add():
    person_id = request.form.get("person_id") or 1
    name = request.form.get("name", "").strip()
    dosage = request.form.get("dosage", "10mg").strip()
    frequency = request.form.get("frequency", "Once daily").strip()
    time_of_day = request.form.get("time_of_day", "Morning (08:00 AM)").strip()
    instructions = request.form.get("instructions", "").strip()
    if name:
        db.add_medication(person_id, name, dosage, frequency, time_of_day, instructions)
        flash(f"Medication '{name} {dosage}' added to schedule.", "success")
    return redirect(url_for("dashboard", person_id=person_id))


@app.route("/medication/toggle/<int:med_id>", methods=["POST"])
@login_required
def medication_toggle(med_id):
    person_id = request.args.get("person_id")
    db.toggle_medication(med_id)
    return redirect(url_for("dashboard", person_id=person_id) if person_id else url_for("dashboard"))


@app.route("/medication/delete/<int:med_id>", methods=["POST"])
@login_required
def medication_delete(med_id):
    person_id = request.args.get("person_id")
    db.delete_medication(med_id)
    flash("Medication removed from schedule.", "info")
    return redirect(url_for("dashboard", person_id=person_id) if person_id else url_for("dashboard"))


# ==========================================
# ADD RECORD (With AI Health Advisor Trigger)
# ==========================================

@app.route("/add-record", methods=["GET", "POST"])
@login_required
def add_record():
    uid = user_id()
    people_objs = db.get_people_objects(uid)
    requested_person_id = request.args.get("person_id", type=int)
    selected_person = next(
        (person for person in people_objs if person.person_id == requested_person_id),
        people_objs[0] if people_objs else None,
    )

    if request.method == "POST":
        person_name = request.form.get("person_name", "").strip()
        systolic = request.form.get("systolic", "").strip()
        diastolic = request.form.get("diastolic", "").strip()
        pulse = request.form.get("pulse", "").strip()
        notes = request.form.get("notes", "").strip()
        date_str = request.form.get("record_date", "").strip()
        time_str = request.form.get("record_time", "").strip()

        if not person_name:
            flash("Please enter the person's name.", "error")
            return redirect(url_for("add_record", person_id=request.form.get("person_id")))

        try:
            sys_val = int(systolic)
            dia_val = int(diastolic)
        except ValueError:
            flash("Systolic and diastolic must be numbers.", "error")
            return redirect(url_for("add_record", person_id=request.form.get("person_id")))

        pulse_val = "N/A" if not pulse else int(pulse)

        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            t = datetime.strptime(time_str, "%H:%M").time()
        except ValueError:
            d = date.today()
            t = datetime.now().time()

        person_row = db.get_or_create_person(uid, person_name)
        person_id_val = person_row.get("id") or person_row.get("person_id", 1)

        new_row = db.create_record(
            person_id=person_id_val,
            systolic=sys_val,
            diastolic=dia_val,
            pulse_rate=pulse_val,
            notes=notes,
            date_val=d,
            time_val=t,
        )

        flash("Blood pressure record saved successfully.", "success")

        if new_row:
            record_obj = db.row_to_record(new_row)
            category = record_obj.get_bp_category()

            # Generate AI health advice
            recent_rows = db.get_records_for_person(person_id_val)
            recent_records = [db.row_to_record(r) for r in recent_rows][-8:]

            advice = ai_advisor.get_health_advice(
                systolic=sys_val,
                diastolic=dia_val,
                pulse=pulse_val,
                category=category,
                notes=notes,
                recent_history=recent_records,
            )

            session["last_advice"] = advice
            session["last_advice_person"] = person_name
            session["last_advice_reading"] = record_obj.get_summary()
            return redirect(url_for("dashboard", person_id=person_id_val, show_advice=1))

        return redirect(url_for("dashboard", person_id=person_id_val))

    return render_template(
        "add_record.html",
        user=current_user(),
        people=people_objs,
        selected_person=selected_person,
        page="add_record",
    )


# ==========================================
# HISTORY
# ==========================================

@app.route("/history")
@login_required
def history():
    uid = user_id()
    people_objs = db.get_people_objects(uid)
    record_rows = db.get_records_for_user(uid)

    records = [db.row_to_record(r) for r in record_rows]
    names = {p.person_id: p.get_name() for p in people_objs}

    search = request.args.get("q", "").strip().lower()
    person_id = request.args.get("person_id", type=int)
    if person_id not in names:
        person_id = None
    if person_id is not None:
        records = [r for r in records if r.person_id == person_id]
    if search:
        records = [r for r in records if search in names.get(r.person_id, "").lower() or search in (r.get_notes() or "").lower()]

    records.sort(
        key=lambda r: (
            getattr(r, 'record_date', getattr(r, 'date', date.today())),
            getattr(r, 'record_time', getattr(r, 'time', datetime.min.time())),
        ),
        reverse=True,
    )

    return render_template(
        "history.html",
        user=current_user(),
        people=people_objs,
        selected_person=next((p for p in people_objs if p.person_id == person_id), None),
        records=records,
        names=names,
        search=search,
        selected_person_id=person_id,
        page="history",
    )


@app.route("/history/delete/<int:record_id>", methods=["POST"])
@login_required
def delete_record(record_id):
    person_id = request.form.get("person_id", type=int)
    advice_cache.invalidate_record(record_id)
    db.delete_record(record_id, person_id=person_id)
    flash("Record deleted.", "success")
    return redirect(url_for("history", person_id=person_id))


# ==========================================
# PATIENT DETAIL (With 7-Day & Month Toggle)
# ==========================================

@app.route("/patient/<int:person_id>")
@login_required
def patient_detail(person_id):
    uid = user_id()
    people_objs = db.get_people_objects(uid)
    person = next((p for p in people_objs if p.person_id == person_id), None)

    if not person:
        flash("Patient not found.", "error")
        return redirect(url_for("manage_people"))

    period = request.args.get("period", "all")
    all_rows = db.get_records_for_person(person_id)
    all_records = [db.row_to_record(r) for r in all_rows]
    all_records.sort(
        key=lambda r: (
            getattr(r, 'record_date', getattr(r, 'date', date.today())),
            getattr(r, 'record_time', getattr(r, 'time', datetime.min.time())),
        )
    )

    today = date.today()

    # 7-day data
    seven_days_ago = today - timedelta(days=7)
    last7 = [r for r in all_records if getattr(r, 'record_date', getattr(r, 'date', today)) >= seven_days_ago]
    chart_labels_7 = [
        datetime.combine(
            getattr(r, 'record_date', getattr(r, 'date', today)),
            getattr(r, 'record_time', getattr(r, 'time', datetime.min.time())),
        ).strftime("%b %d %H:%M")
        for r in last7
    ]
    chart_systolic_7 = [r.get_systolic() for r in last7]
    chart_diastolic_7 = [r.get_diastolic() for r in last7]

    # Month data
    thirty_days_ago = today - timedelta(days=30)
    last30 = [r for r in all_records if getattr(r, 'record_date', getattr(r, 'date', today)) >= thirty_days_ago]
    chart_labels_month = [
        datetime.combine(
            getattr(r, 'record_date', getattr(r, 'date', today)),
            getattr(r, 'record_time', getattr(r, 'time', datetime.min.time())),
        ).strftime("%b %d")
        for r in last30
    ]
    chart_systolic_month = [r.get_systolic() for r in last30]
    chart_diastolic_month = [r.get_diastolic() for r in last30]

    filtered = all_records
    if period == "week":
        filtered = last7
    elif period == "month":
        filtered = last30

    stats = None
    if filtered:
        total = len(filtered)
        pulses = [r.get_pulse_rate() for r in filtered if isinstance(r.get_pulse_rate(), int)]
        stats = {
            "total": total,
            "avg_sys": sum(r.get_systolic() for r in filtered) / total,
            "avg_dia": sum(r.get_diastolic() for r in filtered) / total,
            "avg_pulse": sum(pulses) / len(pulses) if pulses else None,
            "latest": filtered[-1],
            "highest_sys": max(filtered, key=lambda r: r.get_systolic()),
            "lowest_sys": min(filtered, key=lambda r: r.get_systolic()),
        }

    return render_template(
        "patient_detail.html",
        user=current_user(),
        people=people_objs,
        selected_person=person,
        person=person,
        records=filtered,
        total_count=len(all_records),
        period=period,
        stats=stats,
        chart_labels_7=chart_labels_7,
        chart_systolic_7=chart_systolic_7,
        chart_diastolic_7=chart_diastolic_7,
        chart_labels_month=chart_labels_month,
        chart_systolic_month=chart_systolic_month,
        chart_diastolic_month=chart_diastolic_month,
        page="manage_people",
        patient_detail_view=True,
    )


# ==========================================
# MONTHLY SUMMARY
# ==========================================

@app.route("/monthly-summary")
@login_required
def monthly_summary():
    uid = user_id()
    people_objs = db.get_people_objects(uid)

    if not people_objs:
        return render_template(
            "monthly_summary.html",
            user=current_user(),
            people=[],
            page="monthly_summary",
        )

    selected_person_id = request.args.get("person_id", type=int) or people_objs[0].person_id
    selected_month = request.args.get("month", type=int) or date.today().month
    selected_year = request.args.get("year", type=int) or date.today().year

    person = next((p for p in people_objs if p.person_id == selected_person_id), people_objs[0])

    record_rows = db.get_records_for_person(person.person_id)
    monthly_rows = []
    for r in record_rows:
        d_val = r.get("date")
        if isinstance(d_val, str):
            d = datetime.strptime(d_val, "%Y-%m-%d").date()
        else:
            d = d_val
        if d.month == selected_month and d.year == selected_year:
            monthly_rows.append(r)

    monthly = [db.row_to_record(r) for r in monthly_rows]
    monthly.sort(
        key=lambda r: (
            getattr(r, 'record_date', getattr(r, 'date', date.today())),
            getattr(r, 'record_time', getattr(r, 'time', datetime.min.time())),
        )
    )

    summary = MonthlySummary(monthly) if monthly else None

    chart_labels = [
        datetime.combine(
            getattr(r, 'record_date', getattr(r, 'date', date.today())),
            getattr(r, 'record_time', getattr(r, 'time', datetime.min.time())),
        ).strftime("%b %d %H:%M")
        for r in monthly
    ]
    chart_systolic = [r.get_systolic() for r in monthly]
    chart_diastolic = [r.get_diastolic() for r in monthly]

    return render_template(
        "monthly_summary.html",
        user=current_user(),
        people=people_objs,
        selected_person=person,
        selected_month=selected_month,
        selected_year=selected_year,
        monthly=monthly,
        summary=summary,
        chart_labels=chart_labels,
        chart_systolic=chart_systolic,
        chart_diastolic=chart_diastolic,
        page="monthly_summary",
    )


# ==========================================
# MANAGE PEOPLE
# ==========================================

@app.route("/manage-people")
@login_required
def manage_people():
    uid = user_id()
    people_objs = db.get_people_objects(uid)
    record_rows = db.get_records_for_user(uid)

    counts = {}
    for r in record_rows:
        pid = r.get("person_id")
        counts[pid] = counts.get(pid, 0) + 1

    people_info = [
        {"person": p, "record_count": counts.get(p.person_id, 0)}
        for p in people_objs
    ]

    return render_template(
        "manage_people.html",
        user=current_user(),
        people=people_objs,
        people_info=people_info,
        page="manage_people",
    )


@app.route("/manage-people/add", methods=["POST"])
@login_required
def add_person():
    uid = user_id()
    name = request.form.get("name", "").strip()
    age = request.form.get("age", "").strip()
    gender = request.form.get("gender", "Unspecified").strip()
    if not name:
        flash("Patient name is required.", "error")
    else:
        p_age = int(age) if age and age.isdigit() else 45
        db.create_person(uid, name, age=p_age, gender=gender)
        flash(f"Patient profile '{name}' added successfully.", "success")
    return redirect(url_for("manage_people"))


@app.route("/manage-people/delete/<int:person_id>", methods=["POST"])
@login_required
def delete_person(person_id):
    db.delete_person(person_id)
    flash("Person and all records deleted.", "success")
    return redirect(url_for("manage_people"))


# ==========================================
# PDF EXPORT (With Period Selection: 7-day, Month, All)
# ==========================================

@app.route("/patient/<int:person_id>/pdf")
@login_required
def patient_pdf(person_id):
    uid = user_id()
    people_objs = db.get_people_objects(uid)
    person = next((p for p in people_objs if p.person_id == person_id), None)
    if not person:
        flash("Patient not found.", "error")
        return redirect(url_for("manage_people"))

    period = request.args.get("period", "all")
    records = _filtered_records(person_id, period)

    period_labels = {
        "week": "Last 7 Days",
        "month": "Month (Last 30 Days)",
        "all": "All Historical Records",
    }
    timeframe_label = period_labels.get(period, "All Historical Records")

    # Optional advice
    advice = session.get("last_advice")

    buffer = pdf_export.build_patient_pdf(
        person_name=person.get_name(),
        person_id=person.person_id,
        records=records,
        advice=advice,
        timeframe_label=timeframe_label,
    )
    filename = f"BPulse_{safe_filename(person.get_name())}_{period}_{date.today().strftime('%Y%m%d')}.pdf"

    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/patient/<int:person_id>/csv")
@login_required
def patient_csv(person_id):
    uid = user_id()
    people_objs = db.get_people_objects(uid)
    person = next((p for p in people_objs if p.person_id == person_id), None)
    if not person:
        flash("Patient not found.", "error")
        return redirect(url_for("manage_people"))

    period = request.args.get("period", "all")
    records = _filtered_records(person_id, period)

    buffer = csv_export.records_to_csv(person.get_name(), person.person_id, records)
    filename = f"BPulse_{safe_filename(person.get_name())}_{date.today().strftime('%Y%m%d')}.csv"

    return send_file(
        BytesIO(buffer.getvalue().encode("utf-8-sig")),
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


def _filtered_records(person_id, period):
    rows = db.get_records_for_person(person_id)
    records = [db.row_to_record(r) for r in rows]
    records.sort(
        key=lambda r: (
            getattr(r, 'record_date', getattr(r, 'date', date.today())),
            getattr(r, 'record_time', getattr(r, 'time', datetime.min.time())),
        )
    )

    today = date.today()
    if period == "week":
        cutoff = today - timedelta(days=7)
        return [r for r in records if getattr(r, 'record_date', getattr(r, 'date', today)) >= cutoff]
    elif period == "month":
        cutoff = today - timedelta(days=30)
        return [r for r in records if getattr(r, 'record_date', getattr(r, 'date', today)) >= cutoff]
    return records


# ==========================================
# AI ADVISOR (On-Demand & Diagnostics)
# ==========================================

@app.route("/reading/<int:record_id>/advice", endpoint="reading_advice")
@app.route("/reading/<int:record_id>/ai-advice", endpoint="ai_advice_endpoint", methods=["GET", "POST"])
@login_required
def reading_advice(record_id):
    uid = user_id()
    people_objs = db.get_people_objects(uid)
    person_ids = {p.person_id for p in people_objs}

    rows = db.get_records_for_user(uid)
    target_row = next((r for r in rows if r["id"] == record_id), None)

    if not target_row:
        flash("Reading not found.", "error")
        return redirect(url_for("dashboard"))

    record_obj = db.row_to_record(target_row)
    recent_rows = db.get_records_for_person(target_row["person_id"])
    recent_records = [db.row_to_record(r) for r in recent_rows][-8:]

    advice = ai_advisor.get_health_advice(
        systolic=record_obj.get_systolic(),
        diastolic=record_obj.get_diastolic(),
        pulse=record_obj.get_pulse_rate(),
        category=record_obj.get_bp_category(),
        notes=record_obj.get_notes(),
        recent_history=recent_records,
    )

    session["last_advice"] = advice
    session["last_advice_person"] = next(
        (p.get_name() for p in people_objs if p.person_id == target_row["person_id"]),
        "Patient",
    )
    session["last_advice_reading"] = record_obj.get_summary()

    return redirect(url_for("dashboard", person_id=target_row["person_id"], show_advice=1))


@app.route("/advice/dismiss", methods=["POST"])
@login_required
def dismiss_advice():
    for k in ("last_advice", "last_advice_person", "last_advice_reading"):
        session.pop(k, None)
    return redirect(request.referrer or url_for("dashboard"))


# ==========================================
# B-PAL AI CHATBOT ROUTE
# ==========================================

@app.route("/api/bpal/chat", methods=["POST"])
@login_required
def bpal_chat():
    from flask import jsonify
    data = request.get_json(silent=True) or {}
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"reply": "Hello! I am B-Pal, your cardiovascular companion. Ask me anything about your blood pressure readings, medications, or heart-healthy habits!"})

    uid = user_id()
    people_objs = db.get_people_objects(uid)
    pid = request.args.get("person_id")
    target_person = None
    if pid:
        target_person = next((p for p in people_objs if str(p.person_id) == str(pid)), None)
    if not target_person and people_objs:
        target_person = people_objs[0]

    records = []
    medications = []
    if target_person:
        rows = db.get_records_for_person(target_person.person_id)
        records = [db.row_to_record(r) for r in rows]
        medications = db.get_medications_for_person(target_person.person_id)

    reply = ai_advisor.chat_with_bpal(
        user_message=user_msg,
        person=target_person,
        records=records,
        medications=medications,
    )
    return jsonify({"reply": reply})


# ==========================================
# JINJA FILTERS
# ==========================================

@app.template_filter("hhmm")
def format_time(t):
    if not t:
        return ""
    if hasattr(t, "strftime"):
        return t.strftime("%I:%M %p")
    return str(t)[:5]


@app.template_filter("pretty_date")
def pretty_date(d):
    if not d:
        return ""
    if hasattr(d, "strftime"):
        return d.strftime("%b %d, %Y")
    return str(d)


@app.template_filter("bp_category")
def bp_category(record):
    return record.get_bp_category()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000, debug=True)
