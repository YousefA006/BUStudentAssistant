"""Text normalisation and tokenisation for English + Arabic keyword search."""
import re
import unicodedata

_AR_MARKS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")  # harakat + tatweel
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_TOKEN = re.compile(r"[a-z0-9]+|[ء-ي]+")
_ARABIC_CHAR = re.compile(r"[؀-ۿ]")

EN_STOP = set("""a an the and or but if of to in on at by for with from as is are was were be been being
this that these those it its into than then there here what which who whom whose when where why how
do does did can could should would may might will shall i you he she we they me my your our their
about please tell show give any all some not no yes""".split())
AR_STOP = set("""في من الى على عن مع هذا هذه ذلك تلك التي الذي الذين هو هي هم انا انت نحن ما ماذا متى
اين كيف لماذا هل او ثم قد كان كانت يكون لا لم لن ان اذا كل بعض عند بين حتى ايضا""".split())

_AR_PREFIXES = ("وال", "بال", "كال", "فال", "لل", "ال")
_AR_SUFFIXES = ("ها", "ات", "ان", "ون", "ين", "يه", "ه", "ي")


_FARSI_TO_ARABIC = str.maketrans({"ی": "ي", "ى": "ى", "ک": "ك", "ھ": "ه", "ە": "ه", "ۀ": "ه", "ہ": "ه", "ۃ": "ة"})
_MIRROR = str.maketrans("()[]{}<>«»", ")(][}{><»«")
_AR_PUNCT = ".,:;!?()[]«»،؛؟\"'❖●■•-–"


def _reversal_score(words: list[str]) -> tuple[int, int]:
    """(reversed-signals, logical-signals) for the Arabic words of a line.
    Logical Arabic: words start with 'ال' and end with 'ة'/'ى'. Reversed: the mirror image."""
    rev = ok = 0
    for w in words:
        w = w.strip(_AR_PUNCT)
        if len(w) < 2 or not _ARABIC_CHAR.search(w):
            continue
        if w.startswith("ال"):
            ok += 1
        elif w.endswith(("لا", "لأا", "لإا", "لآا")):
            rev += 1
        if w.endswith("ًا"):          # tanween before final alef (حدًا)
            ok += 1
        elif w.startswith("اً"):
            rev += 1
        if w.endswith(("ة", "ى")):
            ok += 1
        elif w.startswith(("ة", "ى")):
            rev += 1
    return rev, ok


def _fix_line(raw: str) -> str:
    """Normalise one extracted line. Some PDF extractors return Arabic in visual (reversed) order;
    detect that and reverse the line BEFORE Unicode normalisation, so lam-alef ligatures stay intact."""
    norm = unicodedata.normalize("NFKC", raw).translate(_FARSI_TO_ARABIC)
    rev, ok = _reversal_score(norm.split())
    if rev == 0 or rev <= ok:
        return norm
    out = []
    for w in reversed(raw.split()):
        if re.search(r"[A-Za-z0-9٠-٩]", w):
            out.append(w)                                  # Latin words and numbers keep their order
        else:
            out.append(w[::-1].translate(_MIRROR))         # Arabic word / punctuation: reverse + mirror brackets
    return unicodedata.normalize("NFKC", " ".join(out)).translate(_FARSI_TO_ARABIC)


def clean_text(text: str) -> str:
    """Display-safe clean-up applied to extracted text (keeps diacritics)."""
    text = "\n".join(_fix_line(l) for l in text.replace("\r\n", "\n").split("\n"))
    text = text.replace("\u00ad", "")
    text = re.sub(r"[ \t\u00a0\u200f\u200e]+", " ", text)
    # extractor artefact: a letter carrying a diacritic split from the rest of its word ("یُ توقع")
    text = re.sub(r"(^|\s)([\u0621-\u064A][\u064B-\u0652]+) (?=[\u0621-\u064A])", r"\1\2", text, flags=re.M)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)  # re-join hyphenated English line breaks
    return text


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = _AR_MARKS.sub("", text)
    text = re.sub("[إأآٱ]", "ا", text)
    text = text.translate(_FARSI_TO_ARABIC)
    text = text.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    return text.translate(_DIGITS).lower()


def _stem_ar(tok: str) -> str:
    for p in _AR_PREFIXES:
        if tok.startswith(p) and len(tok) - len(p) >= 3:
            tok = tok[len(p):]
            break
    else:
        if tok.startswith("و") and len(tok) >= 5:
            tok = tok[1:]
    for s in _AR_SUFFIXES:
        if tok.endswith(s) and len(tok) - len(s) >= 3:
            tok = tok[: -len(s)]
            break
    return tok


def _stem_en(tok: str) -> str:
    if len(tok) <= 3 or tok.isdigit():
        return tok
    for suf, rep in (("ies", "y"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            return tok[: -len(suf)] + rep
    return tok


def tokenize(text: str) -> list[str]:
    out = []
    for tok in _TOKEN.findall(normalize(text)):
        if tok in EN_STOP or tok in AR_STOP:
            continue
        if "ء" <= tok[0] <= "ي":
            tok = _stem_ar(tok)
        else:
            tok = _stem_en(tok)
        if len(tok) >= 2 or tok.isdigit():
            out.append(tok)
    return out


def is_arabic(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if _ARABIC_CHAR.match(c)) / len(letters) > 0.3
