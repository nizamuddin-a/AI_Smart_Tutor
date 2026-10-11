let viewerMode = 1;      // 1, 2 or 3 panes
let panes = [];          // { doc, el, select, frame, empty }
let activePane = 0;

const $ = (id) => document.getElementById(id);

let documents = [];
let quizData = [];
let flashcards = [];
let timerSeconds = 25 * 60;
let timerInterval = null;
let timerRunning = false;

// API helper
async function api(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      data.detail || `Request failed (${response.status})`
    );
  }

  return data;
}

// JSON request helper
function jsonOptions(body) {
  return {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(body)
  };
}

// Get selected document IDs
function selectedDocumentIds() {
  return [
    ...document.querySelectorAll(".doc-check:checked")
  ].map((element) => element.value);
}

// Escape HTML to safely display document names
function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  })[character]);
}

// Display upload status
function setStatus(message) {
  $("uploadStatus").textContent = message;
}

// Check backend connection
async function checkConnection() {
  try {
    await api("/api/health");

    $("connection").textContent = "Backend connected";
    $("connection").classList.remove("offline");
  } catch {
    $("connection").textContent = "Backend disconnected";
    $("connection").classList.add("offline");
  }
}

// ===================== SPLIT VIEWER =====================

// Build the viewer panes for the current layout (1, 2 or 3)
function buildViewer() {
  const grid = $("viewerGrid");
  const previousDocs = panes.map((pane) => pane.doc);

  grid.replaceChildren();
  grid.style.setProperty("--cols", viewerMode);
  panes = [];

  if (activePane >= viewerMode) activePane = 0;

  for (let i = 0; i < viewerMode; i++) {
    const el = document.createElement("div");
    el.className = "viewer-pane";

    const select = document.createElement("select");
    select.setAttribute("aria-label", `Document for pane ${i + 1}`);

    const frame = document.createElement("iframe");
    frame.className = "pane-frame";
    frame.title = `Document viewer pane ${i + 1}`;
    frame.hidden = true;

    const empty = document.createElement("div");
    empty.className = "empty-state";

    el.append(select, empty, frame);
    grid.append(el);

    const pane = { doc: null, el, select, frame, empty };
    panes.push(pane);

    el.addEventListener("click", () => setActivePane(i));
    select.addEventListener("change", () => {
      const doc = documents.find((item) => item.id === select.value) || null;
      setActivePane(i);
      setPaneDoc(i, doc);
    });
  }

  refreshPaneSelects();

  panes.forEach((_, i) => setPaneDoc(i, previousDocs[i] || null));
  setActivePane(activePane);

  document.querySelectorAll("[data-layout]").forEach((button) => {
    button.classList.toggle(
      "active",
      Number(button.dataset.layout) === viewerMode
    );
  });
}

// Highlight the active pane
function setActivePane(index) {
  activePane = index;
  panes.forEach((pane, i) => {
    pane.el.classList.toggle("active", i === index);
  });
}

// Fill each pane's dropdown with the uploaded documents
function refreshPaneSelects() {
  panes.forEach((pane) => {
    const current = pane.doc ? pane.doc.id : "";
    pane.select.replaceChildren();

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "— Choose a document —";
    pane.select.append(placeholder);

    documents.forEach((doc) => {
      const option = document.createElement("option");
      option.value = doc.id;
      option.textContent = doc.name;
      pane.select.append(option);
    });

    pane.select.value = documents.some((doc) => doc.id === current)
      ? current
      : "";
  });
}

// Show a document inside a given pane
function setPaneDoc(index, doc, page) {
  const pane = panes[index];
  if (!pane) return;

  pane.doc = doc;
  pane.select.value = doc ? doc.id : "";

  if (!doc) {
    pane.frame.hidden = true;
    pane.frame.removeAttribute("src");
    pane.empty.hidden = false;
    pane.empty.innerHTML = `
      <div class="empty-icon">↗</div>
      <h3>Empty pane</h3>
      <p>Pick a document from the dropdown, or press <strong>Open</strong> on a document in the sidebar.</p>
    `;
  } else if (doc.extension !== ".pdf") {
    pane.frame.hidden = true;
    pane.frame.removeAttribute("src");
    pane.empty.hidden = false;
    pane.empty.innerHTML = `
      <h3>${escapeHTML(doc.name)}</h3>
      <p>
        Text extracted successfully. Browser preview is currently
        available for PDFs; this file can still be used by the AI tutor.
      </p>
    `;
  } else {
    const pageNumber = Number(page);
    pane.empty.hidden = true;
    pane.frame.hidden = false;
    pane.frame.src =
      `/api/documents/${encodeURIComponent(doc.id)}/file` +
      (Number.isFinite(pageNumber) && pageNumber > 0
        ? `#page=${pageNumber}`
        : "");
  }

  updateViewerTitle();
}

// Show names of all open documents in the header
function updateViewerTitle() {
  const names = panes.filter((pane) => pane.doc).map((pane) => pane.doc.name);
  $("selectedDocName").textContent = names.length
    ? names.join("  |  ")
    : "No document selected";
}

// Open a document (in its existing pane, or in the active pane)
function openDocument(doc, page) {
  const existing = panes.findIndex((pane) => pane.doc && pane.doc.id === doc.id);
  const target = existing !== -1 ? existing : activePane;

  setActivePane(target);
  setPaneDoc(target, doc, page);
}

// ===================== DOCUMENTS =====================

// Load uploaded documents
async function loadDocuments() {
  const result = await api("/api/documents");

  documents = Array.isArray(result)
    ? result
    : (Array.isArray(result.documents) ? result.documents : []);

  // Clear any pane whose document no longer exists
  panes.forEach((pane, i) => {
    if (pane.doc && !documents.some((doc) => doc.id === pane.doc.id)) {
      setPaneDoc(i, null);
    }
  });
  refreshPaneSelects();

  const list = $("documentList");
  list.replaceChildren();

  if (!documents.length) {
    list.textContent =
      "No documents uploaded yet — upload your first file above.";
    list.className = "document-list muted";
    return;
  }

  list.className = "document-list";

  for (const doc of documents) {
    const item = document.createElement("div");
    item.className = "document-item";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "doc-check";
    checkbox.value = doc.id;
    checkbox.checked = true;
    checkbox.setAttribute(
      "aria-label",
      `Use ${doc.name} for AI`
    );

    const name = document.createElement("div");
    name.className = "document-name";
    name.textContent =
      `${doc.name} (${doc.extension || "document"})`;

    const openButton = document.createElement("button");
    openButton.textContent = "Open";
    openButton.className = "secondary";

    openButton.addEventListener("click", () => {
      openDocument(doc);
    });

    item.append(checkbox, name, openButton);
    list.append(item);
  }
}

// Upload files
async function uploadFiles(fileList) {
  const files = [...fileList];

  if (!files.length) return;

  for (const file of files) {
    setStatus(`Uploading ${file.name}...`);

    const form = new FormData();
    form.append("file", file);

    try {
      const result = await api("/api/upload", {
        method: "POST",
        body: form
      });

      setStatus(
        `${result.filename || file.name}: ${result.message || "Upload complete"}`
      );
    } catch (error) {
      setStatus(`${file.name}: ${error.message}`);
    }
  }

  $("fileInput").value = "";

  try {
    await loadDocuments();
    await refreshHistory();
  } catch (error) {
    setStatus(`Upload completed, but refreshing failed: ${error.message}`);
  }
}

// Ask the AI tutor
async function askTutor() {
  const question = $("question").value.trim();

  if (!question) {
    $("answer").textContent = "Enter a question first.";
    return;
  }

  $("askButton").disabled = true;

  $("answer").textContent =
    "Searching your documents and asking the AI...";

  $("citations").replaceChildren();

  try {
    const result = await api(
      "/api/ask",
      jsonOptions({
        question,
        provider: $("provider").value,
        document_ids: selectedDocumentIds()
      })
    );

    $("answer").textContent =
      result?.answer ||
      "The AI returned an empty answer. Please try again.";

    const citations = Array.isArray(result?.citations)
      ? result.citations
      : [];

    for (const citation of citations) {
      const button = document.createElement("button");
      button.className = "citation";

      button.textContent =
        `${citation.document_name || "Document"} · ` +
        `page/slide ${citation.page ?? "?"} — ` +
        `${citation.excerpt || ""}`;

      button.addEventListener("click", () => {
        const doc = documents.find(
          (item) => item.id === citation.document_id
        );

        if (doc) {
          openDocument(doc, citation.page);

          const existing = panes.findIndex(
            (pane) => pane.doc && pane.doc.id === doc.id
          );

          if (existing !== -1) {
            panes[existing].el.scrollIntoView({
              behavior: "smooth",
              block: "start"
            });
          }
        }
      });

      $("citations").append(button);
    }

    await refreshHistory();
  } catch (error) {
    $("answer").textContent = `Error: ${error.message}`;
  } finally {
    $("askButton").disabled = false;
  }
}

// Generate quiz questions
async function generateQuiz() {
  const button = $("generateQuiz");

  button.disabled = true;
  $("quizArea").textContent = "Generating questions...";

  try {
    const result = await api(
      "/api/quiz",
      jsonOptions({
        count: Number($("quizCount").value),
        provider: $("provider").value,
        document_ids: selectedDocumentIds()
      })
    );

    quizData = Array.isArray(result?.questions)
      ? result.questions
      : [];

    renderQuiz();
    await refreshHistory();
  } catch (error) {
    $("quizArea").textContent = `Error: ${error.message}`;
  } finally {
    button.disabled = false;
  }
}

// Display quiz questions
function renderQuiz() {
  const area = $("quizArea");
  area.replaceChildren();

  if (!quizData.length) {
    area.textContent = "No questions were generated.";
    return;
  }

  quizData.forEach((question, index) => {
    const card = document.createElement("div");
    card.className = "quiz-question";

    const heading = document.createElement("h3");
    heading.textContent =
      `${index + 1}. ${question.question || "Question"}`;

    card.append(heading);

    const options = Array.isArray(question.options)
      ? question.options
      : [];

    options.forEach((option, optionIndex) => {
      const label = document.createElement("label");
      label.className = "quiz-option";

      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = `question-${index}`;
      radio.value = optionIndex;

      const text = document.createElement("span");
      text.textContent =
        typeof option === "string"
          ? option
          : (option?.text || "");

      label.append(radio, text);
      card.append(label);
    });

    const feedback = document.createElement("p");
    feedback.className = "quiz-feedback";
    feedback.hidden = true;

    card.append(feedback);

    const check = document.createElement("button");
    check.textContent = "Check answer";

    check.addEventListener("click", () => {
      const chosen = card.querySelector(
        `input[name="question-${index}"]:checked`
      );

      if (!chosen) {
        feedback.hidden = false;
        feedback.textContent = "Choose an answer first.";
        return;
      }

      const selectedIndex = Number(chosen.value);
      const selectedOption = options[selectedIndex];

      const selectedText =
        typeof selectedOption === "string"
          ? selectedOption
          : (selectedOption?.text || "");

      const correctAnswer = question.answer;

      const isCorrect =
        selectedText === correctAnswer ||
        selectedIndex === Number(correctAnswer);

      feedback.hidden = false;

      feedback.className =
        `quiz-feedback ${isCorrect ? "correct" : "incorrect"}`;

      feedback.textContent =
        `${isCorrect ? "Correct!" : "Not quite."} ` +
        `${question.explanation || ""} ` +
        `${question.source ? `Source: ${question.source}` : ""}`;
    });

    card.append(check);
    area.append(card);
  });
}

// Display flashcards
function renderFlashcards() {
  const deck = $("flashcardDeck");
  deck.replaceChildren();

  flashcards.forEach((card, index) => {
    const element = document.createElement("div");
    element.className = "flashcard";

    const front = document.createElement("strong");
    front.textContent = card.front;

    const back = document.createElement("p");
    back.textContent = card.revealed
      ? card.back
      : "Answer hidden";

    const toggle = document.createElement("button");
    toggle.className = "secondary";

    toggle.textContent = card.revealed
      ? "Hide answer"
      : "Show answer";

    toggle.addEventListener("click", () => {
      flashcards[index].revealed =
        !flashcards[index].revealed;

      renderFlashcards();
    });

    element.append(front, back, toggle);
    deck.append(element);
  });
}

// Update focus timer display
function updateTimerDisplay() {
  const minutes = Math.floor(timerSeconds / 60);
  const seconds = timerSeconds % 60;

  $("timerDisplay").textContent =
    `${String(minutes).padStart(2, "0")}:` +
    `${String(seconds).padStart(2, "0")}`;
}

// Stop or pause the timer
function stopTimer() {
  if (timerInterval) {
    clearInterval(timerInterval);
  }

  timerInterval = null;
  timerRunning = false;
}

// Start focus timer
function startTimer() {
  if (timerRunning) return;

  if (timerSeconds <= 0) {
    timerSeconds =
      Math.max(1, Number($("focusMinutes").value) || 25) * 60;
  }

  timerRunning = true;
  $("timerStatus").textContent =
    "Focus session in progress.";

  timerInterval = setInterval(async () => {
    timerSeconds -= 1;
    updateTimerDisplay();

    if (timerSeconds <= 0) {
      stopTimer();

      $("timerStatus").textContent =
        "Session complete! Take a short break.";

      $("timerStatus").scrollIntoView({
        behavior: "smooth",
        block: "nearest"
      });

      try {
        await api(
          "/api/activity",
          jsonOptions({
            activity: "focus_session",
            details:
              `${$("focusMinutes").value} minute session completed`
          })
        );

        await refreshHistory();
      } catch (error) {
        console.error("Could not save focus session:", error);
      }

      alert("Focus session complete! Time for a break.");
    }
  }, 1000);
}

// Reset timer
function resetTimer() {
  stopTimer();

  timerSeconds =
    Math.max(1, Number($("focusMinutes").value) || 25) * 60;

  updateTimerDisplay();
  $("timerStatus").textContent = "Timer reset.";
}

// Load study activity history
async function refreshHistory() {
  try {
    const result = await api("/api/history");

    const entries = Array.isArray(result)
      ? result
      : (Array.isArray(result?.history) ? result.history : []);

    const list = $("historyList");
    list.replaceChildren();

    if (!entries.length) {
      list.textContent =
        "Your study activity will appear here.";
      return;
    }

    entries.forEach((entry) => {
      const item = document.createElement("li");

      item.textContent =
        `${entry.created_at || ""} — ` +
        `${entry.activity || "Activity"}: ` +
        `${entry.details || ""}`;

      list.append(item);
    });
  } catch (error) {
    $("historyList").textContent = error.message;
  }
}

// File upload event
$("fileInput").addEventListener("change", (event) => {
  uploadFiles(event.target.files);
});

// Refresh document list
$("refreshDocs").addEventListener("click", async () => {
  try {
    await loadDocuments();
  } catch (error) {
    setStatus(`Could not load documents: ${error.message}`);
  }
});

// Layout buttons (1 / 2 / 3 panes)
document.querySelectorAll("[data-layout]").forEach((button) => {
  button.addEventListener("click", () => {
    viewerMode = Number(button.dataset.layout) || 1;
    buildViewer();
  });
});

// Ask AI
$("askButton").addEventListener("click", askTutor);

// Clear AI answer and citations
$("clearChat").addEventListener("click", () => {
  $("answer").textContent = "";
  $("citations").replaceChildren();
});

// Generate quiz
$("generateQuiz").addEventListener("click", generateQuiz);

// Save flashcard
$("saveFlashcard").addEventListener("click", () => {
  const front = $("flashcardFront").value.trim();
  const back = $("flashcardBack").value.trim();

  if (!front || !back) {
    alert("Enter both the question and the answer.");
    return;
  }

  flashcards.push({
    front,
    back,
    revealed: false
  });

  $("flashcardFront").value = "";
  $("flashcardBack").value = "";

  renderFlashcards();
});

// Reveal the most recently added flashcard
$("showFlashcard").addEventListener("click", () => {
  if (!flashcards.length) {
    alert("Save a flashcard first.");
    return;
  }

  flashcards[flashcards.length - 1].revealed = true;
  renderFlashcards();
});

// Focus timer controls
$("startTimer").addEventListener("click", startTimer);

$("pauseTimer").addEventListener("click", () => {
  stopTimer();
  $("timerStatus").textContent = "Timer paused.";
});

$("resetTimer").addEventListener("click", resetTimer);

$("focusMinutes").addEventListener("change", () => {
  if (!timerRunning) {
    resetTimer();
  }
});

// Refresh history
$("refreshHistory").addEventListener("click", refreshHistory);

// Initialize application
async function init() {
  updateTimerDisplay();
  buildViewer();
  await checkConnection();

  try {
    await loadDocuments();
    await refreshHistory();
  } catch (error) {
    setStatus(
      `Could not load the application: ${error.message}`
    );
  }
}

init();