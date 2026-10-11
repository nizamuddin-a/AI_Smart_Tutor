# AI Smart Tutor

AI Smart Tutor is an AI-powered study workspace designed to help students learn from their own study materials in one place.

## Features

- **AI Tutor:** Ask questions about your study materials.
- **Document Upload:** Upload supported PDF, PPTX, DOCX, TXT, and Markdown files.
- **Study Assistance:** Get explanations, summaries, examples, and practice questions.
- **Quizzes and Revision:** Support active learning and revision.
- **Focused Workspace:** Bring study resources and AI assistance together.

## Technology

- Python and FastAPI
- HTML, CSS, and JavaScript
- SQLite
- Gemini and Groq APIs

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/nizamuddin-a/AI_Smart_Tutor.git
cd AI_Smart_Tutor
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r backend/requirements.txt
```

### 4. Configure API keys

Create a file named `.env` inside the `backend` folder.

Add your own API keys:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GROQ_API_KEY=your_groq_api_key_here
```

Replace the placeholders with your own keys. Never upload actual API keys to GitHub.

Obtain API keys from the providers' official websites:
- Gemini: https://aistudio.google.com/
- Groq: https://console.groq.com/

### 5. Start the application

From the project root, run:

```bash
python -m uvicorn backend.main:app --reload --reload-dir backend
```

Open the local address displayed by the server in your browser, usually `http://127.0.0.1:8000`.

## Security

API keys, local databases, uploaded documents, and virtual environments should remain private and must not be committed to the repository.

## Project

Built as a student project for learning, experimentation, and hackathon participation.
