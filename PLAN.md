# BU Student Assistant — Hackathon Plan



## 1\. What the guide requires, and our status

### Minimum requirements: all done ✅

|Requirement|Status|
|-|-|
|Ingest PDFs and text, chunk and store for search|✅ 9 file types, structure-aware chunks, 243 passages|
|Retrieve the passages that best match the question|✅ Bilingual multi-query BM25 with rank fusion|
|Answer clearly from the retrieved passages only|✅ Strict prompt plus citation verification|
|Cite the source in every answer (document + page or article)|✅ File, page or lines, section, exact quote, link|
|Refuse without inventing when the documents aren't enough|✅ "I don't know." / "لا أعرف."|
|Understand Arabic, including simple dialect|✅ Query rewriting into Arabic and English (to be tested live, §5)|

### Advanced features: partly done

|Feature|Status|Action|
|-|-|-|
|Evaluate with a test set and measure accuracy|⚠️ Test set written (§5)|**Run it and record "X out of 15" for the slides.** Optional: automated script|
|Hybrid search or reranking|⚠️ Keyword plus bilingual rewriting|Optional: add `multilingual-e5-small` embeddings|
|Remember context and answer follow-ups|✅||
|Combine several documents in one answer|✅|Test Q5|
|Explain with steps or a table|✅||
|Handle conflicts between old and new versions|❌|Mention as future work; we show "Last Reviewed" dates|

### Refusal wording: needs a decision

The guide's example refusal also points the student to the right office, e.g. «لا أجد هذه المعلومة في المستندات المتاحة لي. يرجى مراجعة دائرة القبول والتسجيل». Our assistant currently answers a plain "لا أعرف." **Decision:** keep it plain, or add a polite referral line.

\---

## 2\. Judging criteria (100 + 10 bonus): estimate and actions

|#|Criterion|Marks|Estimate now|Actions to gain marks|
|-|-|-|-|-|
|1|RAG technical quality|30|20–24|Run the test set and show the score; demo a refusal; explain chunking and citation checking|
|2|Problem understanding and fit|15|depends on slides|Survey classmates or find sourced statistics for slide 1; stress Arabic and dialect support|
|3|Code quality and engineering|15|11–13|README ✅, `.env.example` ✅, no keys in code ✅, AI disclosure ✅. Make sure it runs from scratch on another laptop|
|4|Business plan and numbers|15|0 (not started)|Slides 4–6 with **sourced** numbers; label estimates as "افتراض" (assumption)|
|5|Marketing plan|10|0 (not started)|Slide 7: audience, channels, budget, success metrics, 90-day plan|
|6|Presentation and communication|10|depends on delivery|Rehearse the 5-minute demo; every member answers questions|
|7|Innovation|5|3–4|Highlight citation checking, Arabic PDF repair, bilingual search|
|+|Product bonus|+10|8–9|Website ✅ (5), UX/RTL ✅ (2), login and saved chats ✅. Admin panel or FAQ dashboard would complete the 3|

The bonus only counts with **at least 15/30** on criterion 1.

**Deductions to avoid:**

* Made-up numbers or sources.
* **Exposed API keys.** Never submit `.env`, and don't use the first zip from development, which contained a key.
* Copied code without credit.
* Late submission.

The business and marketing criteria are a third of the marks. **Start them by 13:00, not in the last half hour.**

\---

## 3\. System summary (for the judges)

```
Documents → text extraction (+ Arabic repair) → structure-aware chunks (file · page/lines · section)
         → BM25 index (Arabic/English normalisation)
Question (AR / EN / dialect) → LLM rewrites to standalone + EN/AR keywords → BM25 + rank fusion → top 6
         → LLM answers from passages only, as JSON with \[n] markers + verbatim quotes
         → every quote verified against its passage → nothing verified ⇒ "لا أعرف"
```

* **Language model:** Groq `openai/gpt-oss-120b` for answers, `openai/gpt-oss-20b` for query rewriting and as a fallback. The provider is detected from the API key. If a provider retires a model, the app switches automatically.
* **Knowledge base:** 11 documents, 243 passages: the Guidelines PDF (EN+AR), academic regulations, extra guidelines, the Software Engineering plan and course descriptions, and 6 Computer Simulation (CSSE) program pages.
* **Free-tier capacity:** about 2 questions a minute and 50 or more a day. Space demo questions about 30 seconds apart.

\---

## 4\. Test set: run it and record the results

It covers every question type the guide lists (§5 of the guide). For each question, record: **correct answer? correct citation? quote really in the document?**

|#|Type|Question|Expected answer (from our documents)|✔/✘|
|-|-|-|-|-|
|1|Direct (EN)|What is the maximum number of absences for a course that meets twice a week?|4 absences (twice the weekly meetings)||
|2|Direct (AR)|ما الحد الأقصى للغيابات لمساق يعقد مرتين في الأسبوع؟|4 غيابات||
|3|Dialect|شو بصير إذا غبت أكثر من المسموح؟|Exceeding the limit results in a "WF" grade||
|4|Table|كم ساعة معتمدة لمساق CSSE341؟|4 credits (Finite Element Methods I)||
|5|Multi-document|معدلي 2.1 وأنا بسنة ثالثة، كم ساعة أقدر أسجل؟|Normal load is 15–17 credits; exceeding 17 needs a semester GPA ≥ 3.00, so with 2.1 the maximum is 17||
|6|Follow-up (after Q2)|وإذا كان المساق مرة بالأسبوع؟|2 absences||
|7|Direct|When is pre-registration held?|October for Spring, March for Fall||
|8|Cross-language|متى يكون التسجيل المبكر؟|Same as Q7, answered in Arabic||
|9|Program|What are the acceptance-to-major criteria for Computer Simulation (CSSE)?|40 credits; cumulative GPA ≥ 1.90; major GPA ≥ 2.00; English requirements; ≥ 3 major courses (9 credits)||
|10|Program|How many credit hours does the Software Engineering degree require?|131||
|11|Rules|How many times can I change my major?|Once before and once after Acceptance to Major||
|12|Arabic PDF|ما عقوبة الغش في الامتحان؟|Zero in that exam (Guidelines PDF, Arabic page 8)||
|13|Not in documents|متى امتحان مادة الخوارزميات الأسبوع القادم؟|Refusal: «لا أعرف»||
|14|Out of scope|اكتب لي قصيدة عن الجامعة|Refusal: «لا أعرف»||
|15|Not in documents (EN)|What is the tuition fee per credit hour?|Refusal (fees aren't in our documents)||

**Result for the slides:** "Passed \_\_ / 15. Failed: #\_\_ because \_\_." The guide asks for this honest format.

**Retrieval check already done (no LLM):** for 8 typical questions the right passage was in the top 6 every time, and first in 6 of them. For 6 CSSE questions it was in the top 2.

\---

## 5\. Deliverables checklist (guide §8 and §11)

* \[ ] **Code:** zip or GitHub, from the current folder **without** `.env`, `.venv\\` or `storage\\`
* \[x] README with installation, running and architecture
* \[x] `requirements.txt` and `.env.example`
* \[x] AI disclosure in README (team: edit to match your actual use)
* \[x] Data sources listed in README and `data/catalog\_2026-2027/\_SOURCES.md`
* \[x] No API keys inside the code
* \[ ] System answers 3 different questions with sources (test set Q1, Q7, Q10)
* \[ ] Out-of-documents question tried and refused (Q13–Q15)
* \[ ] Runs from scratch following the README, tested on a second laptop
* \[ ] **Slides:** PDF or PPTX, max 12, including the 9 required slides (§7)
* \[ ] Every number in the business plan has a source or is labelled "افتراض"
* \[ ] Every member can explain one part of the code (§9)
* \[ ] Optional: 2–3 minute screen recording (backup if the live demo fails)

\---

## 6\. Presentation: the 9 required slides

|#|Slide|Content|
|-|-|-|
|1|Problem|Who's affected and how big the problem is. **Needs a source or a quick classmate survey.** Use the personas from the guide: Sara (1st year), Ahmad (3rd year, failed a course), Layla (graduating)|
|2|Solution and RAG architecture|The diagram in §4; why bilingual keyword search plus citation checking|
|3|Live demo|Screenshots or video: Q3 (dialect), Q5 (multi-document), Q13 (refusal) with citations; the test-set score|
|4|Market analysis|Market size and target customers, **with sources**|
|5|Revenue model and pricing|Who pays (university, faculty, licence per student?), how much, profit per customer|
|6|Costs and financial projections|API costs, hosting, team; 12–36 month projection; break-even point|
|7|Marketing plan|Audience, channels, approximate budget, success metrics, first 90 days|
|8|Competitors and what sets us apart|Today's alternatives (Registrar's office, PDFs, generic chatbots) vs grounded, cited, bilingual answers|
|9|Team and next steps|Roles (§9) and roadmap (§11)|

\---

## 7\. Demo script (about 5 minutes)

1. **Problem (30 s):** information is scattered across guides, regulations and study plans in two languages, and a wrong answer costs a semester.
2. **Sign up (20 s):** create an account live.
3. **Dialect (60 s):** Q3. Click the citation marker to jump to the quote, then "Open PDF at this page".
4. **Table and program (40 s):** Q4. The answer comes from the CSSE study-plan table.
5. **Multi-document (40 s):** Q5. Two rules, two citations.
6. **Honesty (30 s):** Q13. "لا أعرف". "Our strongest feature is saying I don't know."
7. **Upload (40 s):** drop in a new PDF and ask about it.
8. **Score (20 s):** "Passed \_\_/15 on our test set."

\---

## 8\. Team roles (as the guide suggests)

|Role|Owns|Must be able to explain|
|-|-|-|
|System developer|`llm.py`, `search.py`|Retrieval, prompt, citation verification, fallbacks|
|Interface developer|`static/`, `app.py`|Accounts, upload, Arabic right-to-left interface|
|Data and evaluation|`ingest.py`, `textnorm.py`, `data/`|Chunking, Arabic PDF repair, test set results|
|Presentation and business|Slides 1, 4–8|Market, pricing, costs, marketing, sources|

\---

## 9\. After the hackathon

* Multilingual embeddings for hybrid search, plus a reranker.
* Automated evaluation script.
* Admin panel and most-asked-questions dashboard.
* Polite referral in refusals (which office to contact).
* Version-conflict detection using "Last Reviewed" dates.
* OCR for scanned PDFs.
* HTTPS deployment on a university server; university-email-only sign-up.

