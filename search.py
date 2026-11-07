"""In-memory BM25 keyword index over all chunks, with per-user visibility filtering."""
import math
import threading
from collections import Counter, defaultdict

from db import connect
from textnorm import tokenize

K1, B = 1.5, 0.75


class BM25Index:
    def __init__(self):
        self.lock = threading.Lock()
        self.postings = {}
        self.doc_len = {}
        self.chunk_doc = {}
        self.avg_len = 1.0

    def rebuild(self) -> None:
        postings, doc_len, chunk_doc = defaultdict(dict), {}, {}
        with connect() as conn:
            rows = conn.execute(
                "SELECT c.id, c.document_id, c.section, c.text, d.filename FROM chunks c"
                " JOIN documents d ON d.id = c.document_id"
            ).fetchall()
        for r in rows:
            # file name and section heading are searchable too
            toks = tokenize(f"{r['filename']} {r['section'] or ''} {r['text']}")
            doc_len[r["id"]] = len(toks)
            chunk_doc[r["id"]] = r["document_id"]
            for tok, tf in Counter(toks).items():
                postings[tok][r["id"]] = tf
        with self.lock:
            self.postings, self.doc_len, self.chunk_doc = dict(postings), doc_len, chunk_doc
            self.avg_len = (sum(doc_len.values()) / len(doc_len)) if doc_len else 1.0

    def search(self, query: str, allowed_docs: set, k: int = 20) -> list[tuple[int, float]]:
        terms = set(tokenize(query))
        with self.lock:
            n = len(self.doc_len)
            scores = defaultdict(float)
            for t in terms:
                plist = self.postings.get(t)
                if not plist:
                    continue
                idf = math.log(1 + (n - len(plist) + 0.5) / (len(plist) + 0.5))
                for cid, tf in plist.items():
                    if self.chunk_doc[cid] not in allowed_docs:
                        continue
                    dl = self.doc_len[cid]
                    scores[cid] += idf * tf * (K1 + 1) / (tf + K1 * (1 - B + B * dl / self.avg_len))
        return sorted(scores.items(), key=lambda x: -x[1])[:k]


INDEX = BM25Index()


def hybrid_retrieve(queries: list[str], allowed_docs: set, top_k: int) -> list[int]:
    """Run several queries (e.g. English + Arabic rewrites) and fuse them with reciprocal-rank fusion."""
    fused = defaultdict(float)
    for q in queries:
        for rank, (cid, _score) in enumerate(INDEX.search(q, allowed_docs, k=25)):
            fused[cid] += 1.0 / (60 + rank)
    return [cid for cid, _ in sorted(fused.items(), key=lambda x: -x[1])[:top_k]]
