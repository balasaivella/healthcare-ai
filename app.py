from flask import Flask, render_template, request, jsonify
import requests
import os
import json

# ENV VARIABLES
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# FIREBASE SETUP

import firebase_admin
from firebase_admin import credentials, firestore

db = None

try:
    firebase_key_str = os.environ.get("FIREBASE_KEY")

    if firebase_key_str:
        firebase_key = json.loads(firebase_key_str)
        cred = credentials.Certificate(firebase_key)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ Firebase connected")
    else:
        print("⚠️ FIREBASE_KEY not found")

except Exception as e:
    print("🔥 Firebase Error:", e)

# FLASK APP
app = Flask(__name__)

#SAFETY RISK CHECK

def analyze_symptoms(user_input):
    text = user_input.lower()

    high = [
        "chest pain", "can't breathe", "cannot breathe",
        "breathing difficulty", "unconscious",
        "severe bleeding", "heart attack"
    ]

    medium = [
        "fever", "vomiting", "abdominal pain",
        "headache", "infection"
    ]

    if any(word in text for word in high):
        return "HIGH"
    elif any(word in text for word in medium):
        return "MEDIUM"
    else:
        return "LOW"

# AI RESPONSE

def get_ai_response(user_message, language):
    try:
        url = "https://openrouter.ai/api/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }

        # Language mapping
        lang_map = {
            "hi-IN": "Hindi",
            "te-IN": "Telugu",
            "en-US": "English"
        }
        lang_name = lang_map.get(language, "English")

        system_prompt = f"""
You are an emergency medical triage AI.

Understand mixed language (Hinglish, Telugu-English).

Your job:
1. Identify problem
2. Classify risk: HIGH, MEDIUM, LOW
3. Suggest doctor
4. Give first aid

STRICT FORMAT:

RISK: <HIGH/MEDIUM/LOW>
DOCTOR: <doctor>
STEPS:
- step 1
- step 2
- step 3

Respond only in {lang_name}.
"""

        data = {
            "model": "openai/gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]
        }

        response = requests.post(url, headers=headers, json=data, timeout=10)

        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            print("AI ERROR:", response.text)
            return "⚠️ AI not responding properly."

    except Exception as e:
        print("AI Exception:", e)
        return "⚠️ Server error."

# ROUTES

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_input = request.json.get("message", "")
        language = request.json.get("language", "en-US")

        #  SAFETY FIRST (rule-based)
        safety_level = analyze_symptoms(user_input)

        # AI response
        ai_reply = get_ai_response(user_input, language)

        # Default values
        level = safety_level
        doctor = "General Doctor"

        # ai values
        if ai_reply:
            if "RISK: HIGH" in ai_reply.upper():
                level = "HIGH"
            elif "RISK: MEDIUM" in ai_reply.upper():
                level = "MEDIUM"

            if "DOCTOR:" in ai_reply:
                try:
                    doctor = ai_reply.split("DOCTOR:")[1].split("\n")[0].strip()
                except:
                    pass

        # SAVE IT TO FIREBASE
        if db:
            try:
                db.collection("triage_chats").add({
                    "user": user_input,
                    "ai": ai_reply,
                    "level": level,
                    "doctor": doctor,
                    "language": language
                })
            except Exception as e:
                print("Firestore Error:", e)

        return jsonify({
            "reply": ai_reply,
            "level": level,
            "doctor": doctor
        })

    except Exception as e:
        print("CHAT ERROR:", e)
        return jsonify({
            "reply": "⚠️ Something went wrong",
            "level": "LOW",
            "doctor": "General Doctor"
        })

@app.route('/history')
def history():
    try:
        if not db:
            return jsonify([])

        docs = db.collection("triage_chats").stream()
        data = [doc.to_dict() for doc in docs]

        return jsonify(data)

    except Exception as e:
        print("History Error:", e)
        return jsonify([])

#RUN
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
