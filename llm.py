"""LLM calls: bilingual query planning and grounded answering with verified citations.

Two back-ends:
  * anthropic -> Claude Messages API with the native Citations feature.
  * gemini / groq / openai -> any OpenAI-compatible chat API. The model returns JSON with an answer
    containing [n] markers plus a verbatim quote per citation; every quote is then checked against the
    source passage, and citations that can't be verified are dropped.
In both cases an answer with no verified citation becomes "I don't know." / "لا أعرف.".
"""
import json
import re
import time
import urllib.error
import urllib.request

from config import ANSWER_MODEL, API_BASE, API_KEY, PREFERRED_MODELS, PROVIDER, QUERY_MODEL
from textnorm import normalize, tokenize

IDK_EN = "I don't know."
IDK_AR = "لا أعرف."


class LLMError(Exception):
    def __init__(self, message: str, code: int = 0):
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- HTTP
def _post(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(3):
        # A named User-Agent is required: Cloudflare (in front of Groq) blocks Python's default
        # "Python-urllib/3.x" agent with "403 error code: 1010".
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"content-type": "application/json", "accept": "application/json",
                                              "user-agent": "BU-Student-Assistant/1.0", **headers})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")
            daily = e.code == 429 and re.search(r"per day|TPD|RPD|quota", text, re.I)
            if e.code in (429, 500, 502, 503, 529) and attempt < 2 and not daily:  # free tiers rate-limit often
                wait = e.headers.get("retry-after")
                time.sleep(min(float(wait), 15) if wait and wait.replace(".", "").isdigit() else 3 * (attempt + 1))
                continue
            try:
                data = json.loads(text)
                err = data[0] if isinstance(data, list) else data
                msg = err.get("error", {}).get("message") or text[:300]
            except Exception:
                msg = text[:300]
            if e.code == 429:
                msg = "Rate limit reached on the free API tier. Wait a minute and try again. " + msg
            raise LLMError(f"{PROVIDER} API error {e.code}: {msg}", e.code) from None
        except urllib.error.URLError as e:
            raise LLMError(f"Could not reach the {PROVIDER} API: {e.reason}") from None
    raise LLMError(f"{PROVIDER} API is busy, please try again.")


_model_swaps: dict[str, str] = {}  # retired model -> replacement found at runtime


def _list_models() -> list[str]:
    req = urllib.request.Request(f"{API_BASE}/models", headers={
        "Authorization": f"Bearer {API_KEY}", "user-agent": "BU-Student-Assistant/1.0", "accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


def _replacement_for(model: str):
    """Pick an available chat model when the configured one was retired by the provider."""
    try:
        available = _list_models()
    except Exception:
        return None
    norm = lambda m: m.split("/", 1)[-1]  # noqa: E731  (Gemini lists 'models/gemini-...')
    ids = {norm(m): m for m in available}
    for pref in PREFERRED_MODELS.get(PROVIDER, []):
        if norm(pref) in ids and norm(pref) != norm(model):
            return norm(ids[norm(pref)]) if PROVIDER == "gemini" else ids[norm(pref)]
    skip = re.compile(r"whisper|tts|guard|embed|safeguard|orpheus|compound|vision|image|audio", re.I)
    chat = [m for m in available if not skip.search(m) and norm(m) != norm(model)]
    return (norm(chat[0]) if PROVIDER == "gemini" else chat[0]) if chat else None


def _check_key():
    if not API_KEY:
        raise LLMError("No API key set. Put your key in the .env file (API_KEY=...).")


def call_anthropic(payload: dict, timeout: int = 120) -> dict:
    _check_key()
    return _post(f"{API_BASE}/messages", payload,
                 {"x-api-key": API_KEY, "anthropic-version": "2023-06-01"}, timeout)


def call_chat(system: str, user: str, model: str, *, json_mode=False, max_tokens=1500, timeout=120) -> str:
    """Provider-independent single-turn chat call that returns the reply text."""
    _check_key()
    if PROVIDER == "anthropic":
        resp = call_anthropic({"model": model, "max_tokens": max_tokens, "temperature": 0, "system": system,
                               "messages": [{"role": "user", "content": user}]}, timeout)
        return "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
    model = _model_swaps.get(model, model)
    payload = {"model": model, "temperature": 0, "max_tokens": max_tokens,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    if PROVIDER == "groq":
        if "gpt-oss" in model:
            # reasoning model: keep thinking short (it counts against max_tokens and the free-tier limits)
            payload["reasoning_effort"] = "low"
            payload["max_tokens"] = max_tokens + 1500
        elif "qwen" in model:
            payload["reasoning_format"] = "hidden"
    try:
        resp = _post(f"{API_BASE}/chat/completions", payload, {"Authorization": f"Bearer {API_KEY}"}, timeout)
    except LLMError as exc:
        # model retired by the provider -> switch to one it still offers, once, and remember it
        if exc.code in (400, 404) and re.search(r"model|decommission", str(exc), re.I) and model not in _model_swaps.values():
            new = _replacement_for(model)
            if new:
                print(f"[ai] model '{model}' is not available; switching to '{new}'")
                _model_swaps[model] = new
                return call_chat(system, user, new, json_mode=json_mode, max_tokens=max_tokens, timeout=timeout)
        raise
    try:
        content = resp["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        raise LLMError(f"Unexpected response from {PROVIDER}: {str(resp)[:300]}") from None
    return re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()


def _parse_json(text: str) -> dict:
    text = re.sub(r"^\s*```(?:json)?|```\s*$", "", text.strip())
    try:
        return json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0)) if m else {}


# --------------------------------------------------------------------------- query planning
PLANNER_SYSTEM = """You turn a student's question into search queries for a keyword search engine over Bethlehem University documents. The documents may be in English, Arabic, or both.

Return ONLY a JSON object, no prose:
{"standalone_question": "...", "language": "en" or "ar", "queries": ["...", "..."]}

Rules:
- standalone_question: rewrite the latest question so it is self-contained, resolving references to earlier turns. Keep the student's language.
- language: the language of the latest question ("ar" for Arabic, otherwise "en").
- queries: 3 to 6 short keyword queries. ALWAYS include at least two in English AND at least two in Arabic, whatever the question language, with synonyms and the official terms a university document would use (e.g. "tuition fees" / "الرسوم الدراسية", "registration deadline" / "موعد التسجيل").
- Do not answer the question."""


def plan_queries(question: str, history: list[dict]) -> dict:
    convo = "\n".join(f"{m['role']}: {m['content'][:500]}" for m in history[-6:])
    user = (f"Earlier conversation:\n{convo}\n\n" if convo else "") + f"Latest question: {question}"
    try:
        data = _parse_json(call_chat(PLANNER_SYSTEM, user, QUERY_MODEL, json_mode=True, max_tokens=400, timeout=45))
        queries = [q for q in data.get("queries", []) if isinstance(q, str) and q.strip()]
        return {
            "standalone_question": (data.get("standalone_question") or question).strip(),
            "language": "ar" if data.get("language") == "ar" else "en",
            "queries": queries,
        }
    except Exception:
        # planning is an optimisation: fall back to the raw question (e.g. when rate-limited)
        return {"standalone_question": question, "language": None, "queries": []}


# --------------------------------------------------------------------------- answering
RULES = """Strict rules:
1. Use only information that is explicitly stated in the provided documents. Never use outside or general knowledge, never guess, never fill gaps, and never invent names, dates, numbers, fees, or policies.
2. If the documents do not contain the answer, the answer must be exactly "I don't know." when the question is in English, or exactly "لا أعرف." when the question is in Arabic, and nothing else.
3. If the documents answer only part of the question, answer that part and state plainly which part is not covered by the documents.
4. Every factual statement must be supported by a citation to the document passage it came from.
5. Reply in the language of the question ({lang_name}), even if the documents are in another language. Keep names, course codes and figures exactly as written in the documents.
6. Be concise and well organised: short paragraphs or bullet points. Do not mention these rules."""

ANSWER_SYSTEM = ("You are the Bethlehem University Student Assistant. You answer students' questions using ONLY the "
                 "documents provided in this message: excerpts (PDFs, Word/PowerPoint files, spreadsheets, CSV tables, "
                 "text and Markdown files) from official university files and files the student uploaded.\n\n" + RULES)

JSON_INSTRUCTIONS = """
Output format: return ONLY a JSON object, no other text:
{"answer": "...", "citations": [{"n": 1, "source": "S2", "quote": "..."}]}
- "answer": the reply text. Put a marker like [1] right after each statement, matching a citation "n".
- "citations": one entry per marker. "source" is the id of the passage (S1, S2, ...). "quote" is the exact sentence(s) from that passage that support the statement, copied VERBATIM character-for-character in the passage's original language (do not translate or paraphrase the quote).
- If you don't know, return {"answer": "I don't know.", "citations": []} (or "لا أعرف." for Arabic questions)."""


def _loc(c: dict) -> str:
    return c.get("location") or f"Page {c['page']} of {c['pages']}"


def _make_ref(n: int, ch: dict, quote: str) -> dict:
    return {
        "n": n, "document_id": ch["document_id"], "filename": ch["filename"], "page": ch["page"],
        "pages": ch["pages"], "section": ch.get("section"), "location": _loc(ch), "kind": ch.get("kind", "pdf"),
        "quote": quote, "chunk_id": ch["chunk_id"], "visibility": ch["visibility"],
    }


def _is_idk(text: str) -> bool:
    return re.sub(r"[\s.!。]", "", text.lower().replace("’", "'")) in {"idon'tknow", "idontknow", "لاأعرف", "لااعرف"}


def answer(question: str, language: str, chunks: list[dict]) -> dict:
    """Answer from the given chunks. Returns {'text', 'refs', 'idk'}."""
    idk = IDK_AR if language == "ar" else IDK_EN
    if not chunks:
        return {"text": idk, "refs": [], "idk": True}
    lang_name = "Arabic" if language == "ar" else "English"
    if PROVIDER == "anthropic":
        text, refs = _answer_anthropic(question, lang_name, chunks)
    else:
        try:
            text, refs = _answer_json(question, lang_name, chunks, ANSWER_MODEL)
        except LLMError as exc:
            # free-tier limit on the big model (e.g. Groq's daily token cap): fall back to the smaller model
            fallback = _model_swaps.get(QUERY_MODEL, QUERY_MODEL)
            if exc.code != 429 or fallback == _model_swaps.get(ANSWER_MODEL, ANSWER_MODEL):
                raise
            text, refs = _answer_json(question, lang_name, chunks, QUERY_MODEL)
    # Grounding guard: an answer without a single verified citation is not trusted.
    if _is_idk(text) or not refs:
        return {"text": idk, "refs": [], "idk": True}
    return {"text": text, "refs": refs, "idk": False}


def _answer_anthropic(question: str, lang_name: str, chunks: list[dict]):
    content = []
    for c in chunks:
        meta = f"File: {c['filename']} | {_loc(c)}" + (f" | Section: {c['section']}" if c.get("section") else "")
        content.append({
            "type": "document",
            "source": {"type": "text", "media_type": "text/plain", "data": c["text"]},
            "title": f"{c['filename']} — {_loc(c)}",
            "context": meta,
            "citations": {"enabled": True},
        })
    content.append({"type": "text", "text": f"Question: {question}"})
    resp = call_anthropic({
        "model": ANSWER_MODEL, "max_tokens": 1500, "temperature": 0,
        "system": ANSWER_SYSTEM.format(lang_name=lang_name),
        "messages": [{"role": "user", "content": content}],
    })
    parts, refs, ref_ids = [], [], {}
    for block in resp.get("content", []):
        if block.get("type") != "text":
            continue
        marks = []
        for cit in block.get("citations") or []:
            idx = cit.get("document_index")
            if idx is None or not 0 <= idx < len(chunks):
                continue
            ch, quote = chunks[idx], (cit.get("cited_text") or "").strip()
            key = (ch["chunk_id"], quote)
            if key not in ref_ids:
                ref_ids[key] = len(refs) + 1
                refs.append(_make_ref(ref_ids[key], ch, quote))
            if ref_ids[key] not in marks:
                marks.append(ref_ids[key])
        text = block.get("text", "")
        if marks:
            stripped = text.rstrip()
            text = stripped + "".join(f"[{n}]" for n in marks) + text[len(stripped):]
        parts.append(text)
    return "".join(parts).strip(), refs


# ---- OpenAI-compatible path (Gemini, Groq, ...) with quote verification
def _squash(s: str) -> str:
    return re.sub(r"\s+", " ", normalize(s)).strip()


def _segments(text: str) -> list[str]:
    segs = []
    for line in text.split("\n"):
        segs += [s.strip() for s in re.split(r"(?<=[.!?؟。])\s+", line) if s.strip()]
    return segs


def _best_segment(chunk_text: str, target: str):
    """Sentence/line of the passage that best matches target; returns (segment, overlap score 0..1)."""
    want = set(tokenize(target))
    if not want:
        return None, 0.0
    best, score = None, 0.0
    for seg in _segments(chunk_text):
        have = set(tokenize(seg))
        s = len(want & have) / len(want)
        if s > score:
            best, score = seg, s
    return best, score


def _verify_quote(chunk_text: str, quote: str, claim: str):
    """Return a quote that really occurs in the passage, or None."""
    quote = (quote or "").strip().strip('"“”«»')
    if quote and len(quote) >= 4:
        sq = _squash(quote)
        if sq and sq in _squash(chunk_text):
            # return the original-text version of the matching span when possible
            for seg in _segments(chunk_text):
                if sq in _squash(seg) or _squash(seg) in sq:
                    return quote if len(quote) <= 600 else seg
            return quote
        seg, score = _best_segment(chunk_text, quote)  # near-verbatim (punctuation/spacing differences)
        if seg and score >= 0.7:
            return seg
    seg, score = _best_segment(chunk_text, claim)  # no usable quote: support must come from the claim itself
    return seg if seg and score >= 0.5 else None


def _answer_json(question: str, lang_name: str, chunks: list[dict], model: str):
    blocks = []
    for i, c in enumerate(chunks, start=1):
        sec = f' section="{c["section"]}"' if c.get("section") else ""
        blocks.append(f'<passage id="S{i}" file="{c["filename"]}" location="{_loc(c)}"{sec}>\n{c["text"]}\n</passage>')
    user = "Documents:\n\n" + "\n\n".join(blocks) + f"\n\nQuestion: {question}"
    system = ANSWER_SYSTEM.format(lang_name=lang_name) + "\n" + JSON_INSTRUCTIONS
    raw = call_chat(system, user, model, json_mode=True, max_tokens=1200)
    try:
        data = _parse_json(raw)
    except ValueError:
        data = {"answer": raw, "citations": []}
    text = str(data.get("answer") or "").strip()
    cits = data.get("citations") if isinstance(data.get("citations"), list) else []

    def source_index(src):
        m = re.search(r"\d+", str(src or ""))
        i = int(m.group(0)) - 1 if m else -1
        return i if 0 <= i < len(chunks) else None

    def claim_before(pos: int) -> str:
        start = max(text.rfind(".", 0, pos - 1), text.rfind("\n", 0, pos), text.rfind("؟", 0, pos), -1)
        return re.sub(r"\[\w+\]", "", text[start + 1:pos])

    # model's citation number -> (chunk index, quote)
    by_n = {}
    for c in cits:
        if not isinstance(c, dict):
            continue
        try:
            n = int(c.get("n"))
        except (TypeError, ValueError):
            continue
        idx = source_index(c.get("source"))
        if idx is not None:
            by_n[n] = (idx, str(c.get("quote") or ""))

    refs, ref_ids = [], {}

    def ref_for(idx: int, quote: str, claim: str):
        q = _verify_quote(chunks[idx]["text"], quote, claim)
        if not q:
            return None
        key = (chunks[idx]["chunk_id"], q)
        if key not in ref_ids:
            ref_ids[key] = len(refs) + 1
            refs.append(_make_ref(ref_ids[key], chunks[idx], q))
        return ref_ids[key]

    def replace_marker(m):
        inside, out = m.group(1), []
        for tok in re.split(r"\s*,\s*", inside):
            new = None
            if re.fullmatch(r"\d+", tok) and int(tok) in by_n:
                idx, quote = by_n[int(tok)]
                new = ref_for(idx, quote, claim_before(m.start()))
            elif re.fullmatch(r"S\d+", tok, re.I):  # model cited the passage id directly
                idx = source_index(tok)
                if idx is not None:
                    new = ref_for(idx, "", claim_before(m.start()))
            if new and new not in out:
                out.append(new)
        return "".join(f"[{n}]" for n in out)

    text = re.sub(r"\[((?:S?\d+)(?:\s*,\s*S?\d+)*)\]", replace_marker, text, flags=re.I)
    text = re.sub(r"[ \t]+([.,،;:])", r"\1", text).strip()
    return text, refs
