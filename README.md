# المرشد الأكاديمي الذكي — BU Student Assistant

**IEEE RAG Hackathon at Bethlehem University · Smart Academic Advisor challenge**

A bilingual (Arabic / English) RAG assistant that answers students' academic questions **only from Bethlehem University documents**. Every answer cites its source (document, page or lines, section, and the exact quoted passage). When the documents don't contain the answer, it refuses with **"I don't know." / "لا أعرف."** instead of inventing one.

It runs as a website with accounts, document upload, saved conversations, and a right-to-left Arabic interface in Bethlehem University's colours.

---

## 1. Challenge requirements and how they're met

### Minimum requirements (from the participants' guide)
| Requirement | How it's met |
|---|---|
| Ingest PDFs or document text, chunk and store for search | `ingest.py` reads PDF, Word, PowerPoint, Excel, CSV, TXT, Markdown, HTML and JSON, splits by document structure (headings), and stores passages with their location in SQLite |
| Retrieve the passages most relevant to the question | `search.py`: BM25 keyword search with Arabic normalisation, run on several English **and** Arabic rewrites of the question, merged with reciprocal-rank fusion |
| Generate a clear answer from the retrieved passages only | `llm.py`: a strict prompt ("answer only from the passages; otherwise say I don't know") |
| Cite the source in every answer: document and page or section | Every claim carries a numbered citation showing the file, page (PDF) or lines, section heading and exact quote, with a link that opens the file |
| Refuse when the documents aren't enough, without inventing | Every quote is checked against its source passage. Unverifiable citations are dropped, and an answer with no verified citation becomes "I don't know." / "لا أعرف." |
| Understand Arabic questions, including simple dialect | The question is rewritten into a standalone form plus Arabic and English keyword queries before searching; answers come in the question's language |

### Advanced features
| Feature | Status |
|---|---|
| Remember conversation context and answer follow-up questions | ✅ The last turns are used to rewrite follow-ups into standalone questions |
| Combine more than one document in one answer | ✅ Up to 6 passages from any documents; each claim is cited separately |
| Explain an answer in steps or a table | ✅ Answers use lists and steps; spreadsheet and table rows are indexed as "Column: value" pairs |
| Hybrid search or reranking | ⚠️ Partial: multi-query keyword search with rank fusion; no vector embeddings yet |
| Evaluate the system with a test question set | ⚠️ Manual test set in `PLAN.md` §5; an automated scoring script is still to be done |
| Handle conflicts between old and new document versions | ❌ Not handled automatically. Each passage shows its source and "Last Reviewed" date |

### Product bonus
| Item | Status |
|---|---|
| Working product | ✅ Website (Flask) |
| UX and design, Arabic and right-to-left support | ✅ Full Arabic/English interface switch, right-to-left layout, Bethlehem University colours and crest, mobile layout |
| Productivity features | ✅ Login and accounts, saved chat history, document upload (private or shared). ❌ No admin panel or most-asked-questions dashboard yet |

---

## 2. Installation and running

**Requirements:** Windows with Python 3.10 or newer (python.org, tick "Add Python to PATH"), internet access, and a free LLM API key.

```
1. Copy .env.example to .env, then put your key in it:  API_KEY=gsk_...
2. Put the university documents in the  data\  folder (subfolders allowed)
3. Double-click  run.bat   (first run creates .venv and installs requirements.txt)
4. Open  http://127.0.0.1:5000  and create an account
```

`run.bat` creates `.env` from `.env.example` on first run and opens it in Notepad.

Manual start on any operating system:
```
python -m venv .venv
.venv\Scripts\activate          (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python app.py
```

### Settings (`.env`)
| Variable | Meaning | Default |
|---|---|---|
| `API_KEY` | LLM API key. **The provider is detected from the key**: `gsk_` Groq, `AIza` Gemini, `sk-ant-` Claude | — |
| `PROVIDER` | Optional override: `groq`, `gemini`, `anthropic`, `openai` | auto |
| `ANSWER_MODEL` / `QUERY_MODEL` | Optional model overrides | Groq: `openai/gpt-oss-120b` / `openai/gpt-oss-20b` |
| `DATA_DIR` | Folder of shared documents | `data` |
| `TOP_K` | Passages sent to the model per question | `6` |
| `MAX_UPLOAD_MB` | Upload size limit | `25` |
| `HOST` / `PORT` | `HOST=0.0.0.0` lets other devices on your network open the site | `127.0.0.1` / `5000` |

API keys live only in `.env`, which is excluded by `.gitignore`. No key appears in the code.

---

## 3. Architecture

```
 Phase 1 · Knowledge preparation (on startup / "Rescan folder" / upload)
 ┌───────────┐   ┌──────────────────────────────┐   ┌──────────────────────────┐   ┌─────────────────┐
 │ Documents │──►│ Extract text                  │──►│ Structure-aware chunking  │──►│ SQLite + BM25   │
 │ PDF, MD,  │   │ PDF layout mode, Arabic        │   │ ≤900 chars, new chunk at  │   │ index with      │
 │ DOCX, XLSX│   │ visual-order repair, ligatures,│   │ each heading, metadata:   │   │ Arabic/English  │
 │ CSV, …    │   │ Persian→Arabic letters,        │   │ file · page/lines ·       │   │ normalisation   │
 └───────────┘   │ header/footer removal          │   │ section                   │   └─────────────────┘
                 └──────────────────────────────┘   └──────────────────────────┘

 Phase 2 · Answering (every question)
 ┌──────────────┐   ┌─────────────────────────┐   ┌────────────────┐   ┌──────────────────────────┐   ┌──────────────────┐
 │ Student      │──►│ Query planner (small LLM)│──►│ Retrieval      │──►│ Answer LLM + strict      │──►│ Citation check    │
 │ question     │   │ standalone question +   │   │ BM25 per query │   │ prompt → JSON: answer    │   │ quotes verified;  │
 │ AR / EN /    │   │ EN + AR keyword queries │   │ + rank fusion  │   │ with [n] + verbatim      │   │ none verified →   │
 │ dialect      │   │ (uses chat history)     │   │ → top 6        │   │ quotes                   │   │ "لا أعرف"         │
 └──────────────┘   └─────────────────────────┘   └────────────────┘   └──────────────────────────┘   └──────────────────┘
```

### Key design decisions
- **Keyword search with bilingual query rewriting, not a vector store.** Students ask in Arabic or dialect while most documents are English. The LLM writes English and Arabic keyword queries, and BM25 matches exact terms such as course codes ("CSSE341"), numbers and rule names. It needs no embedding model, runs instantly on a laptop, and is easy to explain. Adding embeddings is the first planned improvement.
- **Every citation is verified.** The model must return the exact sentence it relied on. The app checks that sentence against the passage it cites. Near-matches are replaced by the real sentence, and inventions are dropped. If nothing verifiable remains, the answer is "I don't know."
- **Chunking follows document structure.** Each course, regulation or study-plan semester becomes its own passage, labelled with its heading. PDF passages never span two pages, so page citations are exact.
- **Arabic PDF repair.** Many PDFs store Arabic in visual (reversed) order. The ingester detects this per line and restores reading order while keeping لا ligatures intact.
- **Provider-agnostic.** It works with Groq, Gemini, Claude or any OpenAI-compatible API, and switches automatically if a provider retires a model.

### Project structure
| File | Role |
|---|---|
| `app.py` | Flask web server: accounts, upload/delete, ask endpoint, chat history |
| `ingest.py` | Text extraction for all file types, chunking with exact locations, indexing of `data/` |
| `textnorm.py` | Arabic/English normalisation and tokenisation; repair of reversed Arabic |
| `search.py` | In-memory BM25 index and reciprocal-rank fusion |
| `llm.py` | LLM calls, prompts, citation verification, rate-limit and model fallback |
| `config.py` | Settings from `.env`; provider auto-detection |
| `db.py` | SQLite schema: users, documents, chunks, messages |
| `static/` | Web interface (HTML/CSS/JS), Bethlehem University crest |
| `data/` | Shared knowledge base (indexed) |
| `cleaned_sources/` | Cleaned catalog pages kept out of the index (duplicates; see `_SOURCES.md`) |
| `storage/` | Created automatically: database, uploaded files, session secret |

---

## 4. Data

| Document | Type | Passages | Notes |
|---|---|---|---|
| General Guidelines for Students (updated 19/01/2026) | PDF, 10 pages (EN p.1–5, AR p.6–10) | 43 | Attendance, excused absence, exams, conduct, online learning |
| `bu_academic_regulations.md` | Markdown | 48 | Catalog 2026–2027 academic regulations, bilingual headings |
| `bu_extra_guidelines.md` | Markdown | 7 | Tardiness, absences, credit totals |
| `bu_swer_program.md` | Markdown, tables | 33 | Software Engineering degree plan |
| `bu_swer_course_descriptions.md` | Markdown | 63 | Software Engineering course descriptions |
| `catalog_2026-2027/programs/computer_simulation_csse/` (6 files) | Markdown, tables | 49 | Computer Simulation in Science & Engineering: description, outcomes, acceptance, degree requirements, courses, study plans |
| **Total** | **11 documents** | **243** | |

**Data handling rules (as required by the guide):**
- Only public university documents are used.
- No real student personal data is stored in the knowledge base.
- No model is trained or fine-tuned: this is RAG only.

Uploaded files are private to the uploader unless they choose "Share with all students".

---

## 5. Supported question types

The test questions and results are in `PLAN.md` §5.


| Type (from the guide) | Example | Expected behaviour |
|---|---|---|
| Direct question | "What is the maximum number of absences for a class meeting twice a week?" | Precise answer with citation |
| Spoken dialect | «شو بصير إذا غبت أكثر من المسموح؟» | Understood through query rewriting; answered in Arabic |
| Needs a table | «كم ساعة معتمدة لمساق CSSE341؟» | Reads the row from the study-plan table |
| Combines documents | «معدلي 2.1 وأنا بسنة ثالثة، كم ساعة أقدر أسجل؟» | Combines the student-load and overload rules, citing each |
| Follow-up | «وإذا كان المساق مرة بالأسبوع؟» | Uses the previous turn |
| Not in the documents | «متى امتحان مادة الخوارزميات؟» | "لا أعرف." |
| Out of scope | «اكتب لي قصيدة عن الجامعة» | "لا أعرف." |

---

## 6. Security and privacy
- **Passwords:** stored only as salted hashes (Werkzeug PBKDF2). Sessions use signed, HTTP-only cookies.
- **Requests:** API requests require a custom header, which blocks cross-site form attacks.
- **Uploads:** files are type-checked (PDF and Office signatures) and size-limited, then stored under random names. Text-type files are served as plain text so they can never run scripts.
- **Access:** each user only sees shared documents and their own uploads.
- **Keys:** API keys stay in `.env`, never in code or Git.

## 7. Known limitations
- Needs internet for the LLM API. It doesn't run fully offline.
- Free-tier rate limits (Groq: about 8,000 tokens a minute and 200,000 a day). The app retries, then falls back to the smaller model.
- Scanned (image-only) PDFs need OCR before they can be searched; the app flags them.
- No vector or semantic search yet. Unusual wording relies on the LLM's keyword rewriting.

---

## 8. AI disclosure

As the hackathon rules require, we disclose the AI tools used:

- **Claude (Anthropic)** helped write and debug the code, design the architecture, clean and organise the catalog data, design the interface, and draft this README and `PLAN.md`. The team reviewed and tested the code and can explain every part of it.
- **The running system** uses **Groq-hosted `openai/gpt-oss-120b`** to write answers and **`openai/gpt-oss-20b`** to rewrite queries. The system also supports Gemini or Claude as the language model.
- **Open-source libraries:** Flask, pypdf, PyMuPDF, openpyxl.

> Team: edit this section to reflect exactly how each member used AI tools.

## 9. Data sources
- **General Guidelines for Students:** Bethlehem University, updated 19/01/2026 (provided).
- **Undergraduate Catalog 2026–2027:** Bethlehem University, https://reg.bethlehem.edu:100/ (public). The academic regulations and program pages (Software Engineering, Computer Simulation in Science and Engineering) come from here. Exact page URLs for the newly added catalog files are listed in `data/catalog_2026-2027/_SOURCES.md`, and every cleaned file begins with its own source URL.
