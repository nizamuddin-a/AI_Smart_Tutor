
import os
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load API keys from backend/.env
load_dotenv(Path(__file__).resolve().parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/"
    "v1beta/models/gemini-2.5-flash:generateContent"
)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"


def _ask_gemini(prompt, system_prompt=None):
    """Send a request to Gemini."""

    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing from backend/.env")

    full_prompt = prompt
    if system_prompt:
        full_prompt = (
            f"Instructions:\n{system_prompt}\n\n"
            f"User request:\n{prompt}"
        )

    response = requests.post(
        GEMINI_URL,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": GEMINI_API_KEY,
        },
        json={
            "contents": [
                {
                    "parts": [{"text": full_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
            },
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"Gemini HTTP {response.status_code}: {response.text[:1000]}"
        )

    data = response.json()
    candidates = data.get("candidates", [])

    if not candidates:
        raise RuntimeError(
            f"Gemini returned no answer: {str(data)[:1000]}"
        )

    parts = candidates[0].get("content", {}).get("parts", [])
    answer = "\n".join(
        part["text"] for part in parts if part.get("text")
    ).strip()

    if not answer:
        raise RuntimeError("Gemini returned an empty answer.")

    return answer


def _ask_groq(prompt, system_prompt=None):
    """Send a request to Groq."""

    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing from backend/.env")

    messages = []

    if system_prompt:
        messages.append(
            {"role": "system", "content": system_prompt}
        )

    messages.append({"role": "user", "content": prompt})

    response = requests.post(
        GROQ_URL,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": messages,
            "temperature": 0.3,
        },
        timeout=60,
    )

    if not response.ok:
        raise RuntimeError(
            f"Groq HTTP {response.status_code}: {response.text[:1000]}"
        )

    data = response.json()
    choices = data.get("choices", [])

    if not choices:
        raise RuntimeError(
            f"Groq returned no answer: {str(data)[:1000]}"
        )

    answer = choices[0].get("message", {}).get("content", "")

    if not answer or not answer.strip():
        raise RuntimeError("Groq returned an empty answer.")

    return answer.strip()


def ask_ai(prompt, system_prompt=None):
    """
    Try Gemini first. If it fails, try Groq.
    Compatible with ask_ai(prompt) and
    ask_ai(prompt, system_prompt).
    """

    errors = []

    try:
        return _ask_gemini(prompt, system_prompt)
    except Exception as exc:
        errors.append(f"Gemini: {exc}")
        print(f"Gemini request failed: {exc}")

    try:
        return _ask_groq(prompt, system_prompt)
    except Exception as exc:
        errors.append(f"Groq: {exc}")
        print(f"Groq request failed: {exc}")

    raise RuntimeError(
        "Both AI providers failed.\n" + "\n".join(errors)
    )


def tutor_prompt(question, context=""):
    """Create a prompt for the AI tutor."""

    return f"""
You are a helpful AI tutor for college students.

Answer the student's question clearly and accurately.
Explain difficult concepts in simple language.
Use step-by-step explanations and examples where useful.
If document context is provided, prioritize that context.
Do not invent information that is not supported by the context.
If the context does not contain the answer, say so clearly.

DOCUMENT CONTEXT:
{context if context else "No document context provided."}

STUDENT QUESTION:
{question}
""".strip()



def quiz_prompt(context, num_questions=5):
    """Generate a quiz in the JSON format expected by the frontend."""

    return f"""
Create exactly {num_questions} multiple-choice questions using ONLY
the study material below.

Return ONLY valid JSON. Do not include Markdown code fences or any
text before or after the JSON.

Use this exact structure:
{{
  "questions": [
    {{
      "question": "Question text",
      "options": [
        {{"text": "Option A"}},
        {{"text": "Option B"}},
        {{"text": "Option C"}},
        {{"text": "Option D"}}
      ],
      "answer": "Option A",
      "explanation": "Brief explanation"
    }}
  ]
}}

Rules:
- "questions" must be an array.
- Every question's "options" must be an array of exactly four objects.
- Every option object must contain a "text" string.
- "answer" must match the text of one of the four options exactly.
- Include a short explanation for each answer.
- Do not invent facts beyond the supplied material.

STUDY MATERIAL:
{context}
""".strip()