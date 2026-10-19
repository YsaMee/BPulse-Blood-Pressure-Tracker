# ai_advisor.py — Clinical Health Recommendations & B-Pal Chatbot via Gemini API
import os
import json
import urllib.request
import urllib.error
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
# Target modern active model: gemini-3.8-flash (with gemini-2.5-flash fallback)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")

# AHA/ACC Categories
ALL_CATEGORIES = {
    "Normal",
    "Elevated",
    "Stage 1 Hypertension",
    "Stage 2 Hypertension",
    "Crisis",
    "Hypertensive Crisis",
}

def is_trigger_category(category):
    return True

SYSTEM_PROMPT = """You are a clinical health advisor specializing in cardiovascular hypertension management.
You provide evidence-based, non-prescriptive lifestyle recommendations following American Heart Association (AHA/ACC) guidelines.

CLINICAL CRITERIA:
- Normal: <120/<80 mmHg
- Elevated: 120-129/<80 mmHg
- Stage 1 Hypertension: 130-139 / 80-89 mmHg
- Stage 2 Hypertension: >=140 / >=90 mmHg
- Hypertensive Crisis: >180 and/or >120 mmHg (Emergency evaluation)

IMPORTANT RULES:
- Never diagnose medical conditions or prescribe specific pharmaceutical dosages.
- Keep suggestions specific, encouraging, actionable, and concise.
- If Crisis, set urgency to "emergency". If Stage 2, set urgency to "urgent". If Stage 1, set urgency to "soon". If Normal/Elevated, set urgency to "routine".
- Always end with: "This is informational only. Consult your physician before changing treatment."

Return STRICT JSON matching this schema:
{
  "summary": "1-2 sentence plain-language clinical explanation",
  "urgency": "routine" | "soon" | "urgent" | "emergency",
  "suggestions": [
    {"title": "short title", "detail": "1-2 sentence actionable tip", "category": "diet" | "activity" | "stress" | "monitoring" | "sleep" | "medication-adherence"}
  ],
  "warning_signs": ["symptom 1", "symptom 2"],
  "when_to_seek_help": "one sentence action instruction"
}
Return ONLY valid JSON. Do not include markdown code fences."""


def get_health_advice(systolic, diastolic, pulse, category,
                      notes="", recent_history=None):
    """
    Fetches AI health suggestions using Gemini API with direct REST fallback
    to prevent dependency breakages. Falls back to verified AHA/ACC rule engine.
    """
    recent_history = recent_history or []
    history_summary = ", ".join(
        f"{getattr(r, 'record_date', getattr(r, 'date', ''))} {getattr(r, 'record_time', getattr(r, 'time', ''))} -> {r.get_summary() if hasattr(r, 'get_summary') else ''} ({r.get_bp_category() if hasattr(r, 'get_bp_category') else ''})"
        for r in recent_history[-5:]
    ) or "No prior history provided."

    user_prompt = f"""Patient Blood Pressure Reading:
- Systolic: {systolic} mmHg
- Diastolic: {diastolic} mmHg
- Pulse / Heart Rate: {pulse} bpm
- AHA Classification: {category}
- Clinical Notes: {notes or 'none'}

Recent Reading History (most recent last):
{history_summary}

Provide personalized lifestyle and clinical recommendations following AHA guidelines.
Return strictly valid JSON matching the system schema."""

    # Method 1: Try via standard library urllib REST API call if key exists
    if GEMINI_API_KEY:
        advice_data = _call_gemini_rest(user_prompt)
        if advice_data:
            return advice_data

    # Method 2: Comprehensive clinical fallback rule engine
    return _fallback(category, systolic, diastolic, "Clinical ACC/AHA guidance engine")


def _call_gemini_rest(prompt):
    """Direct REST call to Google Generative Language API using urllib."""
    models_to_try = [GEMINI_MODEL, "gemini-2.5-flash"]
    
    for m in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": f"{SYSTEM_PROMPT}\n\n{prompt}"}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)

                candidates = res_json.get("candidates", [])
                if not candidates:
                    continue

                content_parts = candidates[0].get("content", {}).get("parts", [])
                if not content_parts:
                    continue

                text = content_parts[0].get("text", "").strip()
                if text.startswith("```"):
                    text = text.strip("`")
                    if text.lower().startswith("json"):
                        text = text[4:].strip()

                parsed = json.loads(text)
                parsed.setdefault("summary", "")
                parsed.setdefault("urgency", "routine")
                parsed.setdefault("suggestions", [])
                parsed.setdefault("warning_signs", [])
                parsed.setdefault("when_to_seek_help", "")
                parsed["model_used"] = f"Gemini ({m})"
                return parsed
        except Exception:
            continue
    return None


def _fallback(category, systolic=120, diastolic=80, reason=""):
    """Clinical rule-based advice following ACC/AHA guidelines."""
    lookup = "Hypertensive Crisis" if category in ("Crisis", "Hypertensive Crisis") else category

    base = {
        "Normal": {
            "summary": f"Your reading of {systolic}/{diastolic} mmHg is in the optimal AHA Normal range (<120/<80 mmHg).",
            "urgency": "routine",
            "suggestions": [
                {"title": "Maintain Balanced Nutrition", "detail": "Continue enjoying whole grains, lean proteins, vegetables, and low-sodium choices.", "category": "diet"},
                {"title": "Regular Aerobic Activity", "detail": "Keep up at least 150 minutes of moderate exercise per week to sustain vascular elasticity.", "category": "activity"},
                {"title": "Periodic Verification", "detail": "Log blood pressure monthly to maintain your healthy baseline.", "category": "monitoring"},
            ],
            "warning_signs": ["Sudden dizziness upon standing", "Unexplained heart palpitations"],
            "when_to_seek_help": "Continue routine annual wellness checkups with your physician.",
        },
        "Elevated": {
            "summary": f"Your reading of {systolic}/{diastolic} mmHg is slightly elevated (120-129/<80 mmHg). Early lifestyle habits can prevent progression.",
            "urgency": "routine",
            "suggestions": [
                {"title": "Moderate Sodium Intake", "detail": "Aim for under 2,300 mg of sodium daily (ideally 1,500 mg). Limit processed foods.", "category": "diet"},
                {"title": "Daily 30-min Walking", "detail": "A brisk daily walk can lower systolic blood pressure by 4 to 9 mmHg.", "category": "activity"},
                {"title": "Weekly Tracking", "detail": "Check your reading once or twice weekly in the morning before coffee.", "category": "monitoring"},
            ],
            "warning_signs": ["Persistent tension headaches", "Vision blurriness"],
            "when_to_seek_help": "Recheck in 3 to 6 months and review at your next regular visit.",
        },
        "Stage 1 Hypertension": {
            "summary": f"Reading of {systolic}/{diastolic} mmHg falls in Stage 1 Hypertension (130-139 / 80-89 mmHg). Structured lifestyle modifications are recommended.",
            "urgency": "soon",
            "suggestions": [
                {"title": "DASH Diet Adoption", "detail": "Increase potassium-rich vegetables, fruits, whole grains, and low-fat dairy.", "category": "diet"},
                {"title": "150 min/week Exercise", "detail": "Combine brisk aerobic exercise with 2 days of strength training.", "category": "activity"},
                {"title": "Limit Alcohol & Caffeine", "detail": "Limit alcohol to <=1 drink/day for women, <=2 for men, and avoid caffeine 30 mins before testing.", "category": "diet"},
                {"title": "Schedule Physician Visit", "detail": "Plan a follow-up consultation with your doctor within 1 month.", "category": "monitoring"},
            ],
            "warning_signs": ["Chest tightness", "Shortness of breath on mild exertion", "Severe morning headaches"],
            "when_to_seek_help": "Consult your primary healthcare provider within 1 month.",
        },
        "Stage 2 Hypertension": {
            "summary": f"Reading of {systolic}/{diastolic} mmHg reflects Stage 2 Hypertension (>=140 / >=90 mmHg). Prompt clinical follow-up and active management are indicated.",
            "urgency": "urgent",
            "suggestions": [
                {"title": "Contact Primary Clinic", "detail": "Schedule an appointment with your healthcare provider within 24-48 hours.", "category": "monitoring"},
                {"title": "Strict Sodium Restriction", "detail": "Target under 1,500 mg daily sodium to decrease vascular resistance.", "category": "diet"},
                {"title": "Twice-Daily Log", "detail": "Record readings morning and evening and bring your logbook to your visit.", "category": "monitoring"},
                {"title": "Controlled Breathing", "detail": "Practice 10 minutes of diaphragmatic breathing (6 breaths per minute) to lower sympathetic stress.", "category": "stress"},
            ],
            "warning_signs": ["Chest pain", "Facial numbness or weakness", "Speech difficulty", "Severe pounding headache"],
            "when_to_seek_help": "Contact your doctor's clinic within 1-2 days.",
        },
        "Hypertensive Crisis": {
            "summary": f"CRITICAL: Reading of {systolic}/{diastolic} mmHg exceeds hypertensive crisis thresholds (>180 or >120 mmHg).",
            "urgency": "emergency",
            "suggestions": [
                {"title": "Immediate Medical Evaluation", "detail": "Call emergency medical services (911/local ER) immediately if symptoms are present.", "category": "monitoring"},
                {"title": "Rest Quietly & Retest", "detail": "Sit calmly without talking for 5 minutes, then retake on the opposite arm.", "category": "monitoring"},
                {"title": "Do Not Double Medications", "detail": "Do not take extra medication dosages without direct physician instruction.", "category": "medication-adherence"},
            ],
            "warning_signs": ["Chest pain", "Shortness of breath", "Vision loss or spots", "Numbness or tingling", "Confusion"],
            "when_to_seek_help": "IMMEDIATELY. Go to the nearest emergency department or call emergency services.",
        },
    }

    result = base.get(lookup, base["Stage 1 Hypertension"]).copy()
    result["ai_unavailable_reason"] = reason
    result["model_used"] = "AHA/ACC Clinical Rules Engine"
    return result


# ==============================================================================
# B-PAL: PERSONAL CARDIOVASCULAR AI CHATBOT
# ==============================================================================

BPAL_SYSTEM_PROMPT = """You are B-Pal (Blood Pressure Pal), a warm, highly engaging, empathetic, and medically astute cardiovascular health companion for the BPulse application.

YOUR MISSION:
Transform dry medical numbers into clear, relatable, actionable insights that empower the patient to take control of their heart health.

CORE PERSONALITY & TONE:
- **Warm & Encouraging:** Speak like a supportive health mentor or cardiologist friend. Avoid robotic or dry clinical jargon.
- **Relatable Analogies:** Explain physiological concepts simply (e.g. compare arteries to flexible garden hoses; explain sodium acting like a sponge that holds water in blood vessels).
- **Data-Driven & Observant:** Reference the patient's real numbers, trends, pulse, and medications directly.
- **Action-Oriented Micro-Habits:** Give specific, practical steps (e.g. "Try drinking a glass of water before your morning coffee", "Take a 10-minute stroll after lunch") rather than generic advice.
- **Interactive:** Always close with an engaging, friendly follow-up question or thought-provoking prompt to keep the conversation going!

SAFETY BOUNDARIES:
- Never prescribe prescription drugs or alter medical dosages.
- Always encourage consulting their physician before making treatment changes.
- If severe red flags are described (crushing chest pain, shortness of breath, sudden facial numbness), advise immediate emergency care."""


def chat_with_bpal(user_message, person=None, records=None, medications=None):
    """
    Conversational response generator for B-Pal AI Chatbot.
    Uses Gemini API (gemini-3.8-flash) if available, or a rich cardiovascular expert engine.
    """
    p_name = person.get_name() if person and hasattr(person, 'get_name') else "Patient"
    p_age = person.get_age() if person and hasattr(person, 'get_age') else "50"
    p_gender = person.get_gender() if person and hasattr(person, 'get_gender') else "Unspecified"

    records = records or []
    latest_r = records[-1] if records else None
    latest_sys = latest_r.get_systolic() if latest_r else 124
    latest_dia = latest_r.get_diastolic() if latest_r else 83
    latest_pulse = latest_r.get_pulse_rate() if latest_r and latest_r.get_pulse_rate() else 70
    latest_str = latest_r.get_summary() if latest_r and hasattr(latest_r, 'get_summary') else f"{latest_sys}/{latest_dia} mmHg"
    latest_cat = latest_r.get_bp_category() if latest_r and hasattr(latest_r, 'get_bp_category') else "Stage 1 Hypertension"

    # Compute MAP and Pulse Pressure
    pulse_pressure = latest_sys - latest_dia
    map_val = round((2 * latest_dia + latest_sys) / 3)

    # Summarize history
    if len(records) > 1:
        history_str = " | ".join([f"{r.get_date()}: {r.get_summary()} ({r.get_bp_category()})" for r in records[-5:]])
    else:
        history_str = "Single reading logged so far."

    meds_list = [f"{m.get('name')} {m.get('dosage')} ({m.get('frequency')})" for m in (medications or [])]
    meds_str = ", ".join(meds_list) if meds_list else "None currently registered."

    prompt_context = f"""[Patient Profile & Live Vitals]
Patient Name: {p_name} ({p_age} years old, {p_gender})
Latest Reading: {latest_str} (Pulse: {latest_pulse} bpm, Category: {latest_cat})
Calculated Vitals: Mean Arterial Pressure ~{map_val} mmHg, Pulse Pressure: {pulse_pressure} mmHg
Recent Trend History: {history_str}
Active Medications: {meds_str}

User Question: {user_message}"""

    # 1. Attempt Gemini 3.8 Flash API call
    if GEMINI_API_KEY:
        models_to_try = [GEMINI_MODEL, "gemini-3.8-flash", "gemini-2.5-flash"]
        for m in models_to_try:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI_API_KEY}"
                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": f"{BPAL_SYSTEM_PROMPT}\n\n{prompt_context}"}
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.65,
                        "maxOutputTokens": 700
                    }
                }
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=12) as resp:
                    res_body = resp.read().decode("utf-8")
                    res_json = json.loads(res_body)
                    candidates = res_json.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts and parts[0].get("text"):
                            return parts[0].get("text").strip()
            except Exception as e:
                print(f"[B-Pal] Gemini call error on {m}: {e}")
                continue

    # 2. Rich, Dynamic Cardiovascular Fallback Engine
    # If the user is running without a GEMINI_API_KEY, provide deep, personalized, engaging insights
    msg_lower = user_message.lower()

    if any(k in msg_lower for k in ["what does", "reading", "mean", "numbers", "explain"]):
        return f"""Hey {p_name}! Let's break down your latest reading of **{latest_str}** ({latest_cat}) together!

Think of your circulatory system like a garden hose:
• **Systolic ({latest_sys} mmHg):** The peak pressure wave when your heart squeezes blood through your arteries.
• **Diastolic ({latest_dia} mmHg):** The baseline pressure when your heart relaxes between beats to refill.
• **Pulse Pressure ({pulse_pressure} mmHg):** The difference between the two numbers. An ideal pulse pressure is around 40 mmHg; your current {pulse_pressure} mmHg shows your arterial walls have good responsive tone!

Right now, your numbers are sitting in **{latest_cat}**. This isn't an emergency—it simply means your blood vessels are experiencing slightly more resistance than the ideal target (<120/<80). Often, small lifestyle tweaks like a 15-minute brisk walk after meals and watching sodium can nudge these numbers right back down.

How was your day feeling when this was recorded? Were you relaxed, or had you just been on the go?"""

    elif any(k in msg_lower for k in ["medication", "medicine", "pill", "drug", "dose", "rx", "amlodipine", "losartan", "lisinopril"]):
        return f"""I'm glad you asked about your medications, {p_name}! 

According to your tracker, here is your current regimen:
• **Prescriptions:** {meds_str}

Here is how antihypertensive medications generally work in your body:
1. **Arterial Relaxers (e.g. Amlodipine, Lisinopril, Losartan):** They widen and soften arterial walls so blood flows through with much less resistance.
2. **Fluid Regulators (e.g. Hydrochlorothiazide):** They gently signal your kidneys to excrete excess sodium and water, reducing the total volume your heart has to pump.

💡 **B-Pal Pro-Tip:** Blood pressure follows a natural circadian rhythm—it tends to dip at night and surge in the morning. Taking your doses at the exact same time each day keeps your protective blood levels stable.

Are you experiencing any side effects, or are you looking for tips on building an easy reminder habit?"""

    elif any(k in msg_lower for k in ["lower", "reduce", "drop", "exercise", "walk", "habit", "natural"]):
        return f"""You have tremendous natural power over your blood pressure, {p_name}! Here are 4 scientifically proven habits that move the needle:

1. **The Post-Meal Stroll:** A simple 10–15 minute walk after eating utilizes glucose and encourages your blood vessels to dilate, which can lower your systolic pressure by **4 to 9 mmHg**.
2. **The 4-7-8 Breathing Reset:** Inhale for 4 seconds, hold for 7, and exhale slowly for 8. Doing this for just 3 cycles dampens your sympathetic ("fight or flight") nerve signals and relaxes vascular tone.
3. **Potassium as a Sodium Shield:** Potassium acts like a natural counterbalance to salt. Snacking on an avocado, a banana, or a handful of roasted unsalted pumpkin seeds helps your kidneys flush excess fluid.
4. **Hydration Rhythm:** When you're mildly dehydrated, your blood becomes denser and your body releases vasopressin, causing blood vessels to constrict. Aim for 6–8 glasses of water daily.

Which of these sounds easiest for you to try out today?"""

    elif any(k in msg_lower for k in ["sodium", "salt", "diet", "food", "eat", "dash"]):
        return f"""Nutrition is one of the most effective levers for healthy arteries, {p_name}! 

Here is what the **DASH (Dietary Approaches to Stop Hypertension)** framework suggests:
• **The Sodium Target:** Aim for under **2,300 mg per day** (about 1 level teaspoon of salt across all foods), or an ideal target of **1,500 mg** if you're managing hypertension.
• **Watch the "Hidden Six":** Most sodium doesn't come from your table salt shaker—it hides in packaged breads, cured deli meats, canned soups, pizza, soy sauces, and frozen entrees.
• **Heart-Healthy Heroes:** Fresh leafy greens, berries, oats, walnuts, garlic, and fatty fish (like salmon or tuna) provide nitric oxide boosters that keep your arteries supple.

Do you have a favorite meal you like to cook? I can suggest easy heart-healthy swaps for it!"""

    elif any(k in msg_lower for k in ["headache", "chest pain", "dizzy", "shortness of breath", "vision", "emergency"]):
        return f"""⚠️ **Safety First, {p_name}:**

If you or anyone with you is experiencing:
• Sudden tight chest pressure or radiating pain to the arm/jaw
• Shortness of breath at rest
• Sudden numbness or drooping in the face or limbs
• A severe pounding headache accompanied by blurred vision or dizziness

**Please seek emergency medical evaluation immediately (call 911 or your local emergency hotline).** When blood pressure is accompanied by these symptoms, prompt clinical attention is crucial.

If you are feeling completely normal physically without any symptoms, try sitting quietly for 5 minutes with both feet flat on the floor, take three slow breaths, and retest your reading."""

    else:
        return f"""Hi {p_name}! I'm **B-Pal**, your personal heart health companion.

Looking at your log, your latest reading is **{latest_str}** ({latest_cat}) with a resting pulse of **{latest_pulse} bpm**. Your active medication schedule is: *{meds_str}*.

I can help you with anything from:
• 🩺 **Deciphering your numbers:** What your systolic/diastolic and pulse pressure mean for your arteries.
• 🥗 **Food & DASH Diet:** Practical tips on lowering sodium without sacrificing flavor.
• 🏃 **Daily Energy & Activity:** How simple movement and hydration stabilize your readings.
• 💊 **Medication Support:** Best practices for timing and adherence.

What's on your mind today?"""