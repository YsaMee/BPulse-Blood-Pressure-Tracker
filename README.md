# BPulse - Blood Pressure Tracker

BPulse is a Flask web application for recording and reviewing blood pressure readings. It includes patient profiles, trend charts, medication tracking, monthly summaries, report exports, and an optional AI health-advice experience.

## Features

- Record systolic and diastolic blood pressure, pulse, date, time, and notes.
- Manage patient profiles with separate first, middle, and last names, editable demographics, and medication schedules with per-dose amounts, strength and medicine-form details explained in plain language (strength is displayed but not required), scheduled daily dose counts, and dose-by-dose adherence tracking. As-needed medications can be logged without a daily target.
- Show an emergency-help button for signed-in users and a dashboard alert for crisis-range blood pressure readings, with guidance to seek emergency services when severe symptoms occur. BPulse does not contact responders automatically.
- Search patient profiles throughout the app, search reading history across all patients, and view 7-day or 30-day trends.
- Generate monthly summaries and use the unified export window to download a PDF (with selectable month range and medication log) or a CSV, with an option to include matching AI-advisor recommendations in the PDF.
- Get a concise AI Health Advisor summary with a cached reading trend, then use B-Pal for follow-up questions with recent chat context. Without a Gemini API key, the app uses its built-in rule-based guidance.
- Sidebar navigation places AI Health Advisor directly below Medication Tracker.
- Use local JSON files for development, or configure Supabase for database and authentication services.

## Requirements

- Python 3.10 or newer
- pip

## Run Locally

1. Clone the repository and open its directory:

   ```powershell
   git clone https://github.com/YsaMee/BPulse-Blood-Pressure-Tracker.git
   cd BPulse-Blood-Pressure-Tracker
   ```

2. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   On macOS or Linux, use `python3 -m venv .venv` and `source .venv/bin/activate` instead.

3. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

4. Start the Flask app:

   ```powershell
   python app.py
   ```

5. Open [http://127.0.0.1:3000](http://127.0.0.1:3000) in your browser.

The local JSON store creates sample patient profiles and readings when it is empty. Local data is written under `data/` and is excluded from Git.

## Configuration

The app loads environment variables from a `.env` file in the project directory. The local JSON fallback works without one. Set only the integrations you intend to use:

```dotenv
FLASK_SECRET_KEY=replace-with-a-long-random-secret

# Optional: enables Gemini-backed advice and B-Pal responses
GEMINI_API_KEY=your-gemini-api-key
# GEMINI_MODEL=your-supported-gemini-model

# Optional: configure both to use Supabase instead of the local JSON fallback
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-key
```

Keep `.env` private. Never commit API keys, Supabase keys, credentials, or real patient information. `FLASK_SECRET_KEY` must be set to a private random value before deployment; the built-in development default is not suitable for production.

## Data and Safety

This project is intended for learning and local development. It is not a medical device and its informational advice does not replace professional medical care. Do not use it to diagnose or treat a condition, and do not rely on it in an emergency.

Blood pressure readings and profile information are sensitive health data. Use fictional data for demos, do not publish real patient records, and do not expose the built-in Flask development server to the public internet. A production deployment needs a properly secured server, session configuration, authentication, and data storage setup.
