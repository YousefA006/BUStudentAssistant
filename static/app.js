"use strict";

/* ------------------------------------------------------------------ i18n */
const T = {
  en: {
    appName: "Student Assistant", uni: "Bethlehem University", login: "Log in", register: "Create account",
    name: "Full name", email: "Email", password: "Password", addPdf: "Add documents",
    dropHint: "Drop files here or click to choose", shareAll: "Share with all students",
    knowledge: "Knowledge base", rescan: "Rescan folder", logout: "Log out",
    askTitle: "Ask about your university documents", clear: "Clear chat", welcome: "How can I help?",
    welcomeSub: "I answer only from the documents in the knowledge base and cite the exact location and passage for every answer. If the answer isn't in the documents, I'll tell you I don't know.",
    placeholder: "Ask a question in English or Arabic…", send: "Ask", sources: "Sources",
    page: "Page", of: "of", section: "Section", openPdf: "Open PDF at this page",
    folderDoc: "University folder", sharedUpload: "Shared upload", privateUpload: "Your private upload",
    pages: "pages", passages: "passages", noText: "no text found (scanned?)",
    noDocs: "No documents yet. Put files in the data folder or upload one.",
    thinking: "Searching the documents…", idkNote: "No supporting passage was found in the documents.",
    uploading: "Uploading and indexing", uploaded: "Indexed", del: "Delete", confirmDel: "Delete this file?", openFile: "Open file", slides: "slides",
    rescanDone: "Folder rescanned", confirmClear: "Clear your chat history?", langBtn: "العربية",
  },
  ar: {
    appName: "المساعد الطلابي", uni: "جامعة بيت لحم", login: "تسجيل الدخول", register: "إنشاء حساب",
    name: "الاسم الكامل", email: "البريد الإلكتروني", password: "كلمة المرور", addPdf: "إضافة مستندات",
    dropHint: "اسحب الملفات هنا أو انقر للاختيار", shareAll: "مشاركة مع جميع الطلاب",
    knowledge: "قاعدة المعرفة", rescan: "إعادة فحص المجلد", logout: "تسجيل الخروج",
    askTitle: "اسأل عن مستندات جامعتك", clear: "مسح المحادثة", welcome: "كيف يمكنني مساعدتك؟",
    welcomeSub: "أجيب فقط من المستندات الموجودة في قاعدة المعرفة، وأذكر الموقع والمقطع الدقيق لكل إجابة. إذا لم تكن الإجابة في المستندات فسأقول لا أعرف.",
    placeholder: "اكتب سؤالك بالعربية أو الإنجليزية…", send: "اسأل", sources: "المراجع",
    page: "صفحة", of: "من", section: "القسم", openPdf: "افتح الملف على هذه الصفحة",
    folderDoc: "مجلد الجامعة", sharedUpload: "ملف مرفوع مشترك", privateUpload: "ملفك الخاص",
    pages: "صفحات", passages: "مقاطع", noText: "لا يوجد نص (ملف ممسوح ضوئيًا؟)",
    noDocs: "لا توجد مستندات بعد. ضع الملفات في مجلد البيانات أو ارفع ملفًا.",
    thinking: "جارٍ البحث في المستندات…", idkNote: "لم يتم العثور على مقطع داعم في المستندات.",
    uploading: "جارٍ الرفع والفهرسة", uploaded: "تمت الفهرسة", del: "حذف", confirmDel: "حذف هذا الملف؟", openFile: "افتح الملف", slides: "شرائح",
    rescanDone: "تمت إعادة فحص المجلد", confirmClear: "مسح سجل المحادثة؟", langBtn: "English",
  },
};
let lang = localStorage.getItem("bu-lang") || "en";
const t = (k) => (T[lang] && T[lang][k]) || T.en[k] || k;

function applyLang() {
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === "ar" ? "rtl" : "ltr";
  document.querySelectorAll("[data-i18n]").forEach((el) => (el.textContent = t(el.dataset.i18n)));
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => (el.placeholder = t(el.dataset.i18nPh)));
  document.querySelectorAll(".lang-toggle").forEach((b) => (b.textContent = t("langBtn")));
  setAuthMode(authMode);
  if (currentUser) { renderDocs(); }
}

/* ------------------------------------------------------------------ api */
async function api(path, opts = {}) {
  const headers = { "X-Requested-With": "fetch", ...(opts.headers || {}) };
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(opts.json); }
  const res = await fetch(path, { method: opts.method || "GET", headers, body: opts.body, credentials: "same-origin" });
  let data = {};
  try { data = await res.json(); } catch (_) { /* non-JSON */ }
  if (!res.ok) {
    if (res.status === 401 && path !== "/api/login") showAuth();
    throw new Error(data.error || `Request failed (${res.status})`);
  }
  return data;
}

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

/* ------------------------------------------------------------------ auth */
let currentUser = null;
let authMode = "login";

function setAuthMode(mode) {
  authMode = mode;
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === mode));
  document.querySelectorAll(".reg-only").forEach((el) => el.classList.toggle("hidden", mode !== "register"));
  $("#auth-submit").textContent = t(mode === "login" ? "login" : "register");
  $("#auth-form [name=password]").autocomplete = mode === "login" ? "current-password" : "new-password";
}

function showAuth() {
  currentUser = null;
  $("#app").classList.add("hidden");
  $("#auth").classList.remove("hidden");
}

async function showApp(user) {
  currentUser = user;
  $("#auth").classList.add("hidden");
  $("#app").classList.remove("hidden");
  $("#user-name").textContent = user.name;
  await Promise.all([loadDocs(), loadHistory()]);
  $("#question").focus();
}

$("#auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  const errBox = $("#auth-error");
  errBox.classList.add("hidden");
  try {
    const body = { email: f.get("email"), password: f.get("password") };
    if (authMode === "register") body.name = f.get("name");
    const data = await api(authMode === "login" ? "/api/login" : "/api/register", { method: "POST", json: body });
    e.target.reset();
    showApp(data.user);
  } catch (err) {
    errBox.textContent = err.message;
    errBox.classList.remove("hidden");
  }
});
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => setAuthMode(b.dataset.tab)));
document.querySelectorAll(".lang-toggle").forEach((b) => b.addEventListener("click", () => {
  lang = lang === "en" ? "ar" : "en";
  localStorage.setItem("bu-lang", lang);
  applyLang();
}));
$("#logout-btn").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" }).catch(() => {});
  $("#messages").querySelectorAll(".msg").forEach((m) => m.remove());
  showAuth();
});

/* ------------------------------------------------------------------ documents */
let docs = [];

async function loadDocs() {
  const data = await api("/api/documents");
  docs = data.documents;
  renderDocs();
}

function docOrigin(d) {
  if (d.source === "folder") return t("folderDoc");
  return d.visibility === "shared" ? t("sharedUpload") : t("privateUpload");
}

function docSize(d) {
  if (d.kind === "pdf") return `${d.pages} ${esc(t("pages"))}`;
  if (d.kind === "pptx") return `${d.pages} ${esc(t("slides"))}`;
  return esc((d.kind || "").toUpperCase());
}

function renderDocs() {
  const ul = $("#doc-list");
  if (!docs.length) { ul.innerHTML = `<li class="doc-empty">${esc(t("noDocs"))}</li>`; return; }
  ul.innerHTML = docs.map((d) => `
    <li>
      <span class="doc-icon">▤</span>
      <div class="doc-main">
        <div class="doc-name" dir="auto"><a href="/api/documents/${d.id}/file" target="_blank" rel="noopener">${esc(d.filename)}</a></div>
        <div class="doc-meta">${esc(docOrigin(d))} · ${docSize(d)}
          ${d.status === "no_text" ? ` · <span class="warn">${esc(t("noText"))}</span>` : ` · ${d.chunks} ${esc(t("passages"))}`}</div>
      </div>
      ${d.mine ? `<button class="doc-del" title="${esc(t("del"))}" data-id="${d.id}">✕</button>` : ""}
    </li>`).join("");
  ul.querySelectorAll(".doc-del").forEach((b) => b.addEventListener("click", async () => {
    if (!confirm(t("confirmDel"))) return;
    await api(`/api/documents/${b.dataset.id}`, { method: "DELETE" }).catch((e) => alert(e.message));
    loadDocs();
  }));
}

async function uploadFiles(files) {
  const status = $("#upload-status");
  for (const file of files) {
    const line = document.createElement("div");
    line.textContent = `${t("uploading")}: ${file.name}…`;
    status.prepend(line);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("share", $("#share-check").checked ? "true" : "false");
    try {
      const data = await api("/api/documents", { method: "POST", body: fd });
      line.className = data.document.warning ? "bad" : "ok";
      line.textContent = data.document.warning
        ? `${file.name}: ${data.document.warning}`
        : `✓ ${t("uploaded")}: ${file.name} (${data.document.chunks} ${t("passages")})`;
    } catch (e) {
      line.className = "bad";
      line.textContent = `${file.name}: ${e.message}`;
    }
  }
  loadDocs();
}

for (const id of ["#file-input", "#file-input-2"]) {
  $(id).addEventListener("change", (e) => { uploadFiles([...e.target.files]); e.target.value = ""; });
}
const dz = $("#dropzone");
["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
dz.addEventListener("drop", (e) => uploadFiles([...e.dataTransfer.files]));

$("#rescan-btn").addEventListener("click", async () => {
  const btn = $("#rescan-btn");
  btn.disabled = true;
  try {
    const r = await api("/api/rescan", { method: "POST" });
    const line = document.createElement("div");
    line.className = r.failed.length ? "bad" : "ok";
    line.textContent = `${t("rescanDone")}: +${r.added.length} ~${r.updated.length} −${r.removed.length}` +
      (r.failed.length ? ` · ${r.failed.join("; ")}` : "");
    $("#upload-status").prepend(line);
    await loadDocs();
  } catch (e) { alert(e.message); }
  btn.disabled = false;
});

/* ------------------------------------------------------------------ chat rendering */
let msgCounter = 0;

function renderAnswer(text, msgId) {
  const lines = esc(text).split("\n");
  let html = "", list = null;
  const closeList = () => { if (list) { html += `</${list}>`; list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    let m;
    if ((m = line.match(/^\s*[-*•]\s+(.*)$/))) {
      if (list !== "ul") { closeList(); html += "<ul>"; list = "ul"; }
      html += `<li>${m[1]}</li>`;
    } else if ((m = line.match(/^\s*\d+[.)]\s+(.*)$/))) {
      if (list !== "ol") { closeList(); html += "<ol>"; list = "ol"; }
      html += `<li>${m[1]}</li>`;
    } else if (!line.trim()) {
      closeList();
    } else {
      closeList();
      html += `<p>${line.replace(/^#{1,4}\s+/, "")}</p>`;
    }
  }
  closeList();
  return html
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[(\d{1,3})\]/g, (_, n) => `<a class="cite" href="#ref-${msgId}-${n}" data-ref="ref-${msgId}-${n}">${n}</a>`);
}

const isPdf = (r) => !r.kind || r.kind === "pdf";
const AR_LOC = [[/\bPage\b/g, "صفحة"], [/\bSlide\b/g, "شريحة"], [/\bof\b/g, "من"], [/\bSheet\b/g, "ورقة"],
  [/\b[Rr]ows\b/g, "الصفوف"], [/\b[Rr]ow\b/g, "الصف"], [/\bLines\b/g, "الأسطر"], [/\bLine\b/g, "السطر"],
  [/\bParagraphs\b/g, "الفقرات"], [/\bParagraph\b/g, "الفقرة"]];
function locLabel(r) {
  let s = r.location || `Page ${r.page} of ${r.pages}`;
  if (lang === "ar") for (const [re, ar] of AR_LOC) s = s.replace(re, ar);
  return s;
}

function renderRefs(refs, msgId) {
  if (!refs || !refs.length) return "";
  const origin = (r) => r.visibility === "private" ? t("privateUpload") : "";
  return `<div class="refs"><div class="refs-title">${esc(t("sources"))}</div>` + refs.map((r) => `
    <div class="ref" id="ref-${msgId}-${r.n}">
      <div class="ref-n">${r.n}</div>
      <div class="ref-body">
        <div class="ref-file" dir="auto">${esc(r.filename)}</div>
        <div class="ref-meta">
          <span dir="auto">${esc(locLabel(r))}</span>
          ${r.section ? `<span dir="auto">${esc(t("section"))}: ${esc(r.section)}</span>` : ""}
          ${origin(r) ? `<span>${esc(origin(r))}</span>` : ""}
        </div>
        <blockquote class="ref-quote" dir="auto">${esc(r.quote)}</blockquote>
        <a class="ref-open" href="/api/documents/${r.document_id}/file${isPdf(r) ? `#page=${r.page}` : ""}" target="_blank" rel="noopener">${esc(t(isPdf(r) ? "openPdf" : "openFile"))} ↗</a>
      </div>
    </div>`).join("") + "</div>";
}

function addMessage(role, content, refs, opts = {}) {
  $("#empty").classList.add("hidden");
  const id = ++msgCounter;
  const wrap = document.createElement("div");
  wrap.className = `msg ${role === "user" ? "user" : "bot"}${opts.idk ? " idk" : ""}${opts.error ? " error" : ""}`;
  if (role === "user") {
    wrap.innerHTML = `<div class="bubble" dir="auto">${esc(content)}</div>`;
  } else if (opts.loading) {
    wrap.innerHTML = `<div class="bubble"><span class="typing"><span class="dot"></span><span class="dot"></span><span class="dot"></span> ${esc(t("thinking"))}</span></div>`;
  } else {
    const idk = opts.idk || !(refs && refs.length);
    wrap.innerHTML = `<div class="bubble"><div class="answer" dir="auto">${renderAnswer(content, id)}</div>
      ${idk && !opts.error ? `<div class="idk-note">${esc(t("idkNote"))}</div>` : ""}
      ${renderRefs(refs, id)}</div>`;
    if (idk && !opts.error) wrap.classList.add("idk");
  }
  $("#messages").appendChild(wrap);
  wrap.scrollIntoView({ behavior: "smooth", block: "end" });
  return wrap;
}

$("#messages").addEventListener("click", (e) => {
  const a = e.target.closest(".cite");
  if (a) {
    e.preventDefault();
    const target = document.getElementById(a.dataset.ref);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.classList.add("flash");
      setTimeout(() => target.classList.remove("flash"), 1400);
    }
  }
  const chip = e.target.closest(".chip");
  if (chip) { $("#question").value = chip.textContent; ask(); }
});

async function loadHistory() {
  $("#messages").querySelectorAll(".msg").forEach((m) => m.remove());
  const data = await api("/api/history");
  $("#empty").classList.toggle("hidden", data.messages.length > 0);
  for (const m of data.messages) addMessage(m.role, m.content, m.refs);
}

/* ------------------------------------------------------------------ ask */
let busy = false;
async function ask() {
  const q = $("#question").value.trim();
  if (!q || busy) return;
  busy = true;
  $("#send-btn").disabled = true;
  $("#question").value = "";
  autosize();
  addMessage("user", q);
  const loading = addMessage("bot", "", [], { loading: true });
  try {
    const data = await api("/api/ask", { method: "POST", json: { question: q } });
    loading.remove();
    addMessage("bot", data.answer, data.refs, { idk: data.idk });
  } catch (e) {
    loading.remove();
    addMessage("bot", e.message, [], { error: true });
  }
  busy = false;
  $("#send-btn").disabled = false;
  $("#question").focus();
}

$("#ask-form").addEventListener("submit", (e) => { e.preventDefault(); ask(); });
const autosize = () => { const ta = $("#question"); ta.style.height = "auto"; ta.style.height = Math.min(ta.scrollHeight, 180) + "px"; };
$("#question").addEventListener("input", autosize);
$("#question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask(); }
});
$("#clear-btn").addEventListener("click", async () => {
  if (!confirm(t("confirmClear"))) return;
  await api("/api/history/clear", { method: "POST" });
  loadHistory();
});
$("#menu-btn").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
$("#messages").addEventListener("click", () => $("#sidebar").classList.remove("open"));

/* ------------------------------------------------------------------ boot */
(async () => {
  applyLang();
  try {
    const data = await api("/api/me");
    data.user ? showApp(data.user) : showAuth();
  } catch (_) { showAuth(); }
})();
