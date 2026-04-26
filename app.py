from flask import Flask, render_template, request, jsonify, send_from_directory
import requests
import os
import uuid
from google import genai

app = Flask(__name__)

AUDIO_FOLDER = os.path.join("static", "audio")
os.makedirs(AUDIO_FOLDER, exist_ok=True)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

VOICE_IDS = {
    "en-US": "EXAVITQu4vr4xnSDxMaL",
    "hi-IN": "EXAVITQu4vr4xnSDxMaL",
    "te-IN": "EXAVITQu4vr4xnSDxMaL"
}


def analyze_symptoms(user_input):
    text = user_input.lower()

    high_keywords = [
        "chest pain", "can't breathe", "cannot breathe", "breathing difficulty",
        "shortness of breath", "unconscious", "severe bleeding", "heart attack",
        "stroke", "seizure", "fainted", "fainting", "blood vomiting",
        "not able to breathe", "heavy bleeding", "collapsed"
    ]

    medium_keywords = [
        "headache", "fever", "vomiting", "stomach pain", "abdominal pain",
        "body pain", "infection", "dizziness", "cough", "cold", "weakness",
        "sore throat", "nausea"
    ]

    for word in high_keywords:
        if word in text:
            return "HIGH", "Emergency Doctor"

    for word in medium_keywords:
        if word in text:
            return "MEDIUM", "General Doctor"

    return "LOW", "General Doctor"


def get_ai_reply(user_input, language_code, level):
    if not OPENROUTER_API_KEY:
        return "AI key missing. Please set OPENROUTER_API_KEY."

    prompt = f"""
You are a medical triage assistant.

IMPORTANT:
- Respond ONLY in this language: {language_code}
- If language is te-IN, reply only in Telugu script
- If language is hi-IN, reply only in Hindi
- If language is en-US, reply only in English
- Do not mix languages
- Do not use English when Telugu or Hindi is selected

User symptoms: {user_input}
Risk level: {level}

Rules:
- Keep response short
- Give simple first aid advice
- If HIGH risk, tell the user to get emergency help immediately
- Do not claim a final diagnosis
"""

    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "openai/gpt-4o-mini",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a calm and helpful medical triage assistant."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            },
            timeout=45
        )

        data = response.json()

        if "choices" in data and len(data["choices"]) > 0:
            return data["choices"][0]["message"]["content"].strip()
        else:
            return "⚠️ AI not responding properly."

    except Exception:
        if level == "HIGH":
            return "This may be serious. Please seek emergency medical help immediately."
        elif level == "MEDIUM":
            return "Please consult a doctor soon and monitor your symptoms."
        else:
            return "Please rest, monitor your symptoms, and seek care if they worsen."


def translate_with_gemini(text, language_code):
    if not GEMINI_API_KEY:
        return text

    if language_code == "en-US":
        return text

    language_name = {
        "hi-IN": "Hindi",
        "te-IN": "Telugu"
    }.get(language_code, "English")

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""
Translate this emergency medical guidance into {language_name}.
Keep it short, simple, and clear.
Do not add new medical advice.
Only translate.

Text:
{text}
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        return response.text.strip()

    except Exception:
        return text


def generate_tts_audio(text, language_code):
    if not ELEVENLABS_API_KEY:
        return None

    voice_id = VOICE_IDS.get(language_code, VOICE_IDS["en-US"])
    filename = f"{uuid.uuid4().hex}.mp3"
    filepath = os.path.join(AUDIO_FOLDER, filename)

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }

    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.45,
            "similarity_boost": 0.8,
            "style": 0.35,
            "use_speaker_boost": True
        }
    }

    try:
        r = requests.post(url, json=payload, headers=headers, timeout=60)
        if r.status_code == 200:
            with open(filepath, "wb") as f:
                f.write(r.content)
            return f"/static/audio/{filename}"
        else:
            return None
    except Exception:
        return None


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()

    user_input = data.get("message", "").strip()
    language = data.get("language", "en-US")

    if not user_input:
        return jsonify({
            "reply": "Please enter your symptoms.",
            "level": "LOW",
            "doctor": "General Doctor",
            "audio_url": None
        })

    level, doctor = analyze_symptoms(user_input)

    ai_reply_english = get_ai_reply(user_input, "en-US", level)
    ai_reply = translate_with_gemini(ai_reply_english, language)

    audio_url = generate_tts_audio(ai_reply, language)

    return jsonify({
        "reply": ai_reply,
        "level": level,
        "doctor": doctor,
        "audio_url": audio_url
    })


if __name__ == "__main__":
    app.run(debug=True)
