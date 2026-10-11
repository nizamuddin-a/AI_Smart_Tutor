
import json
import os
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import database
from backend.document_service import (
    extract_document,
    make_chunks,
    retrieve_chunks,
)
from backend.ai_service import ask_ai, tutor_prompt, quiz_prompt

# --------------------------------------------------
# Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BACKEND_DIR / ".env")

app = FastAPI(title="AI Smart Tutor")
database.init_db()


# --------------------------------------------------
# Request models
# --------------------------------------------------

class AskRequest(BaseModel):
    question: str
    document_id: Optional[str] = None
    document_ids: list[str] = Field(default_factory=list)
    provider: Optional[str] = "gemini"


class QuizRequest(BaseModel):
    document_id: Optional[str] = None
    document_ids: list[str] = Field(default_factory=list)
    count: int = Field(default=5, ge=1, le=10)
    provider: Optional[str] = "gemini"


class ActivityRequest(BaseModel):
    activity: str
    details: Optional[str] = ""


# --------------------------------------------------
# Document and AI helpers
# --------------------------------------------------

def get_document_chunks(document_id=None):
    """Load chunks from one document or all saved documents."""
    if document_id:
        document = database.get_document(document_id)

        if not document:
            raise HTTPException(
                status_code=404,
                detail="Document not found. Please upload it again.",
            )

        return document["chunks"]

    chunks = database.get_all_chunks()

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No study material found. Upload a document first.",
        )

    return chunks


def get_relevant_chunks(document_id, question):
    """Retrieve relevant chunks using the existing document service."""
    chunks = get_document_chunks(document_id)
    return retrieve_chunks(chunks, question)


def chunks_to_text(chunks):
    """Turn retrieved chunks into text for the AI."""
    return "\n\n".join(
        f"Page {chunk.get('page', '?')}: {chunk.get('text', '')}"
        for chunk in chunks
        if chunk.get("text", "").strip()
    )


def call_selected_provider(prompt, system_prompt=None, provider=None):
    """Call the selected provider, falling back to ask_ai."""
    selected = (provider or os.getenv("AI_PROVIDER", "gemini")).lower()

    try:
        if selected == "groq":
            from backend.ai_service import _ask_groq
            return _ask_groq(prompt, system_prompt)

        if selected == "gemini":
            from backend.ai_service import _ask_gemini
            return _ask_gemini(prompt, system_prompt)

    except Exception:
        # Try the general provider helper below.
        pass

    return ask_ai(prompt, system_prompt)


def normalize_quiz(raw, requested_count):
    """Parse quiz JSON and standardize options for the frontend."""
    cleaned = raw.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1]
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    if not cleaned.startswith("{"):
        start = cleaned.find("{")
        end = cleaned.rfind("}")

        if start < 0 or end <= start:
            raise ValueError("The AI did not return valid quiz JSON.")

        cleaned = cleaned[start:end + 1]

    quiz = json.loads(cleaned)

    if not isinstance(quiz, dict):
        raise ValueError("Quiz response must be a JSON object.")

    questions = quiz.get("questions")

    if not isinstance(questions, list) or not questions:
        raise ValueError("The AI returned no quiz questions.")

    result = []

    for number, item in enumerate(questions[:requested_count], start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Question {number} is invalid.")

        question_text = item.get("question")
        options = item.get("options")
        answer = item.get("answer", item.get("correct_answer"))
        explanation = item.get("explanation", "")

        if isinstance(options, dict):
            options = list(options.values())

        if not isinstance(options, list) or len(options) != 4:
            raise ValueError(
                f"Question {number} must contain exactly four options."
            )

        option_texts = []

        for option in options:
            if isinstance(option, str):
                value = option
            elif isinstance(option, dict):
                value = option.get(
                    "text", option.get("label", option.get("option"))
                )
            else:
                value = None

            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"Question {number} contains an invalid option."
                )

            option_texts.append(value.strip())

        if not isinstance(question_text, str) or not question_text.strip():
            raise ValueError(f"Question {number} has no question text.")

        if isinstance(answer, str):
            answer = answer.strip()
            if answer.upper() in ("A", "B", "C", "D"):
                answer = option_texts[ord(answer.upper()) - ord("A")]

        if not isinstance(answer, str) or answer not in option_texts:
            raise ValueError(
                f"Question {number} has an invalid correct answer."
            )

        result.append({
            "question": question_text.strip(),
            "options": [{"text": value} for value in option_texts],
            "answer": answer,
            "explanation": (
                explanation if isinstance(explanation, str) else ""
            ),
        })

    if not result:
        raise ValueError("No usable quiz questions were returned.")

    return {"questions": result}


# --------------------------------------------------
# Health
# --------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------
# Documents
# --------------------------------------------------

@app.get("/api/documents")
def list_documents():
    return {"documents": database.get_documents()}


@app.post("/api/upload")
async def upload_document(file: UploadFile = File(...)):
    original_name = Path(file.filename or "document.txt").name
    extension = Path(original_name).suffix.lower()

    allowed = {".pdf", ".docx", ".pptx", ".txt", ".md"}

    if extension not in allowed:
        raise HTTPException(
            status_code=400,
            detail="Supported formats: PDF, DOCX, PPTX, TXT, and MD.",
        )

    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    # Unique stored filename prevents overwriting another upload.
    doc_id = uuid.uuid4().hex
    saved_path = DATA_DIR / f"{doc_id}{extension}"
    saved_path.write_bytes(content)

    try:
        pages = extract_document(str(saved_path), extension)
        chunks = make_chunks(pages)

        if not chunks:
            raise ValueError(
                "No readable text found. Scanned PDFs may need OCR."
            )

        database.save_document(
            doc_id,
            original_name,
            str(saved_path),
            extension,
            chunks,
        )

    except Exception as exc:
        saved_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"Could not process document: {exc}",
        ) from exc

    return {
        "message": "Document uploaded successfully.",
        "document_id": doc_id,
        "filename": original_name,
        "chunks": len(chunks),
    }


@app.get("/api/documents/{document_id}")
def get_document(document_id: str):
    document = database.get_document(document_id)

    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Keep the response smaller; chunks can be requested through preview.
    return {
        "id": document["id"],
        "name": document["name"],
        "extension": document["extension"],
        "created_at": document["created_at"],
    }


@app.get("/api/documents/{document_id}/file")
def document_file(document_id: str):
    document = database.get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    path = Path(document["path"]).resolve()
    if not path.is_file() or DATA_DIR.resolve() not in path.parents:
        raise HTTPException(status_code=404, detail="Document file is unavailable.")
    return FileResponse(path, media_type="application/pdf", filename=document["name"], content_disposition_type="inline")


@app.get("/api/documents/{document_id}/preview")
def preview_document(document_id: str):
    document = database.get_document(document_id)

    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")

    return {
        "document": {
            "id": document["id"],
            "name": document["name"],
            "extension": document["extension"],
            "chunks": document["chunks"],
        }
    }


# --------------------------------------------------
# Ask AI tutor
# --------------------------------------------------

@app.post("/api/ask")
def ask(request: AskRequest):
    question = request.question.strip()

    if not question:
        raise HTTPException(
            status_code=400,
            detail="Please enter a question.",
        )

    selected_ids = request.document_ids or ([request.document_id] if request.document_id else [])
    if selected_ids:
        chunks = []
        for selected_id in selected_ids:
            chunks.extend(get_relevant_chunks(selected_id, question))
        chunks = sorted(chunks, key=lambda item: sum(item.get("text", "").lower().count(term) for term in question.lower().split()), reverse=True)[:5]
    else:
        chunks = get_relevant_chunks(None, question)

    if not chunks:
        raise HTTPException(
            status_code=404,
            detail="No matching content found. Try another question.",
        )

    context = chunks_to_text(chunks)
    prompt = tutor_prompt(question, context)

    try:
        answer = call_selected_provider(
            prompt,
            "Answer using the supplied study material. "
            "If the answer is not in the material, say so.",
            request.provider,
        )

        if not answer:
            raise ValueError("The AI returned an empty answer.")

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"AI provider error: {exc}",
        ) from exc

    try:
        database.log_activity("ask", question)
    except Exception:
        pass

    return {"answer": answer}


# --------------------------------------------------
# Quiz
# --------------------------------------------------

@app.post("/api/quiz")
def create_quiz(request: QuizRequest):
    selected_ids = request.document_ids or ([request.document_id] if request.document_id else [])
    chunks = []
    if selected_ids:
        for selected_id in selected_ids:
            chunks.extend(get_document_chunks(selected_id))
    else:
        chunks = get_document_chunks()

    # Use a broad selection of the document for quiz generation.
    chunks = chunks[:20]
    context = chunks_to_text(chunks)

    if not context.strip():
        raise HTTPException(
            status_code=404,
            detail="The selected document contains no readable text.",
        )

    prompt = quiz_prompt(context, request.count)

    try:
        raw = call_selected_provider(
            prompt,
            "Return only valid JSON matching the requested quiz schema.",
            request.provider,
        )
        quiz = normalize_quiz(raw, request.count)

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not generate quiz: {exc}",
        ) from exc

    try:
        database.log_activity(
            "quiz",
            f"Generated {len(quiz['questions'])} questions",
        )
    except Exception:
        pass

    return quiz


# --------------------------------------------------
# History and activity
# --------------------------------------------------

@app.get("/api/history")
def history():
    return {"history": database.get_history()}


@app.post("/api/activity")
def record_activity(request: ActivityRequest):
    database.log_activity(request.activity, request.details or "")
    return {"message": "Activity recorded."}


# --------------------------------------------------
# Frontend
# --------------------------------------------------

if FRONTEND_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )

