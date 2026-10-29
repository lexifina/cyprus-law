"""Cyprus parse: the cache (Internet Archive copies of CyLaw pages and Gazette PDFs) -> corpus.d/<part>.json.

    python -X utf8 scripts/cyprus-law/parse.py [--report]

Reads only .cache/ and sources.json (written by fetch.py). No network. Deterministic.

How a version is made. CyLaw's consolidated page lists, under each section, the instruments that made or amended
it, oldest first; each entry but the last links to the section's wording as that instrument left it
(`section-<sc>-ln<ln>.html`), and the last is the wording on the page. So the act as it stood after instrument k is:
for each section, the wording under the latest of its instruments up to k (absent if its first instrument is later).
That wording is read from, in order of preference:
  1. the newest consolidated page (for the section's last instrument);
  2. the archived old-wording page of that instrument (`-ln`);
  3. any archived copy of the whole consolidated page whose amendment list ended at an instrument after which the
     section had the same latest instrument (same wording by CyLaw's own history).
A version is built only if every section's wording is found; otherwise it is left out and listed. Because a
missing version would date its changes to the next version's day, an act's history starts at the first version
after which no version is missing; earlier versions are listed, not built.
Every archived full copy is also compared with the version rebuilt for its amendment list (`--report`).
"""
from __future__ import annotations

import hashlib
import html as htmlmod
import json
import re
import sys
from pathlib import Path

import fitz  # PyMuPDF: reads the PDFs' own text layer; no OCR

HERE = Path(__file__).resolve().parent
CACHE = HERE / '.cache'
PARTS = HERE / 'corpus.d'
RETRIEVED = '2026-10-29'


# ---------------------------------------------------------------- cache

def cache_path(ts: str, url: str) -> Path:
    return CACHE / hashlib.sha256(f'https://web.archive.org/web/{ts}id_/{url}'.encode('utf-8')).hexdigest()


def wb_url(ts: str, url: str) -> str:
    return f'https://web.archive.org/web/{ts}id_/{url}'


def read(ts: str, url: str) -> bytes | None:
    p = cache_path(ts, url)
    return p.read_bytes() if p.exists() else None


# ---------------------------------------------------------------- text

QUOTES = str.maketrans({'‘': "'", '’': "'", 'ʼ': "'", '΄': "'", '´': "'", '“': '"',
                        '”': '"', '–': '-', '—': '-', '‐': '-', '‑': '-', ' ': ' ',
                        '\t': ' ', ' ': ' ', ' ': ' ', ' ': ' ', '​': '', '﻿': '',
                        'µ': 'μ', '∆': 'Δ', 'Ω': 'Ω'})  # micro/increment/ohm signs


HOMO_UP = str.maketrans('ABEZHIKMNOPTYX', 'ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ')
HOMO_LATIN = 'ABEZHIKMNOPTYXoóáéí'
HOMO_ALL = str.maketrans(HOMO_LATIN, 'ΑΒΕΖΗΙΚΜΝΟΡΤΥΧοόάέί')
GREEK_CH = re.compile(r'[Ͱ-Ͽἀ-῿]')
LATIN_CH = re.compile(r'[A-Za-zóáéí]')
WORD = re.compile(r'[^\W\d_]+')


def fold_homoglyphs(line: str) -> str:
    """Latin capitals typed for Greek ones (CyLaw corrects these over time: 'Bουλής' -> 'Βουλής'). In a word with
    Greek letters, Latin look-alikes become Greek; a short all-capital Latin look-alike word between Greek words
    ('O γενικός') does too. Other Latin text (EU titles, '(I)' in law numbers) is left alone."""
    words = list(WORD.finditer(line))
    out, last = [], 0
    for i, m in enumerate(words):
        w = m.group(0)
        new = w
        if GREEK_CH.search(w) and LATIN_CH.search(w):
            if all(c in HOMO_LATIN for c in LATIN_CH.findall(w)):
                new = w.translate(HOMO_ALL)
        elif len(w) <= 3 and all(c in 'ABEZHIKMNOPTYX' for c in w):
            prev = words[i - 1].group(0) if i else ''
            nxt = words[i + 1].group(0) if i + 1 < len(words) else ''
            between = line[words[i - 1].end():m.start()] if i else ''
            if GREEK_CH.search(nxt) and (not prev or GREEK_CH.search(prev)) and '(' not in between[-1:]:
                new = w.translate(HOMO_UP)
        out.append(line[last:m.start()] + new)
        last = m.end()
    out.append(line[last:])
    return ''.join(out)


def lines_of(fragment: str) -> list[str]:
    """CyLaw HTML -> one paragraph per line, typesetting normalised (spaces, quotes, dashes)."""
    t = re.sub(r'(?is)<script.*?</script>|<style.*?</style>', '', fragment)
    t = re.sub(r'(?i)<br\s*/?>|</p>|</div>|</li>|</tr>|</h\d>', '\n', t)
    t = re.sub(r'<[^>]+>', '', t)
    t = htmlmod.unescape(t).translate(QUOTES)
    out = []
    for line in t.split('\n'):
        line = fold_homoglyphs(re.sub(r' +', ' ', line).strip())
        if line:
            out.append(line)
    return out


def norm_label(s: str) -> str:
    s = re.sub(r'\s+', '', htmlmod.unescape(re.sub(r'<[^>]+>', '', s)))
    s = s.replace('Ι', 'I')  # Greek capital iota is used for the Latin "(I)" in some entries
    return re.sub(r'^(\d+)\(1\)/', r'\1(I)/', s)  # '83(1)/2008' is CyLaw's typo for 83(I)/2008


# ---------------------------------------------------------------- pages

SEC_START = re.compile(r'<div class="full-section(?: repeal)?">\s*<a name="(sc[0-9a-f-]+)"')


def parse_page(raw: bytes) -> dict:
    h = raw.decode('cp1253', 'replace')
    sb = h[h.find('sidebar-history-header'):h.find('main-content')]
    instruments = [norm_label(x) for x in re.findall(
        r'<li[^>]*>\s*(?:<span class="toc-instrument-enum">)?(.+?)\s*(?:</span>)?\s*</li>', sb, re.S)]
    main = h[h.find('<div class="main-content">'):]
    end = len(main)
    for stop in ('<div class="full-appendices-title"', '<div class="footnote-title"', '<div id="ui-tab-separator"'):
        i = main.find(stop)
        if i >= 0:
            end = min(end, i)
    body, tail = main[:end], main[end:]
    starts = list(SEC_START.finditer(body))
    sections = []
    for i, m in enumerate(starts):
        blk = body[m.start():starts[i + 1].start() if i + 1 < len(starts) else len(body)]
        head = re.search(r'full-section-header">(.*?)</div>', blk, re.S)
        ts = blk.find('full-section-text">')
        te = blk.find('<div class="full-section-history"')
        text = blk[ts + len('full-section-text">'):te if te > 0 else len(blk)]
        text = re.sub(r'(\s*</div>)+\s*$', '', text.rstrip())
        hist = []
        if te > 0:
            for li in re.findall(r'<li class="toc-instrument">(.*?)</li>', blk[te:], re.S):
                a = re.search(r'href="([^"]+)"', li)
                hist.append((norm_label(li), a.group(1) if a else None))
        sections.append({'id': m.group(1), 'header': ' '.join(lines_of(head.group(1))) if head else '',
                         'lines': lines_of(text), 'hist': hist, 'repeal': 'full-section repeal' in blk[:60]})
    pre = re.search(r'<div class="preamble current">(.*?)</div>\s*</div>', body, re.S)
    annexes = []
    for m in re.finditer(r'<div class="appendix-enum">(.*?)</div>\s*<div class="appendix-text">(.*?)</div>\s*'
                         r'(?=<div class="appendix-enum"|</div>|<div id="ui-tab|<div class="footnote)', tail, re.S):
        annexes.append({'title': ' '.join(lines_of(m.group(1))), 'lines': lines_of(m.group(2))})
    return {'instruments': instruments, 'sections': sections,
            'preamble': lines_of(pre.group(1)) if pre else None, 'annexes': annexes}


# ---------------------------------------------------------------- unit keys

GREEK = ['Α', 'Β', 'Γ', 'Δ', 'Ε', 'ΣΤ', 'Ζ', 'Η', 'Θ', 'Ι', 'Κ', 'Λ', 'Μ', 'Ν', 'Ξ', 'Ο', 'Π', 'Ρ', 'Σ', 'Τ', 'Υ',
         'Φ', 'Χ', 'Ψ', 'Ω']
LATIN_LOOK = str.maketrans('ABEZHIKMNOPTYX', 'ΑΒΕΖΗΙΚΜΝΟΡΤΥΧ')


def suffix_key(s: str) -> str:
    s = s.translate(LATIN_LOOK).upper()
    out, i = [], 0
    while i < len(s):
        if s[i:i + 2] == 'ΣΤ':
            out.append('f'); i += 2; continue
        out.append(chr(ord('a') + GREEK.index(s[i])) if s[i] in GREEK else '')
        i += 1
    return ''.join(out)


def section_number(act: dict, sec: dict) -> tuple[int, str] | None:
    if act['numbered_by'] == 'header':
        m = re.match(r'ΑΡΘΡΟΝ\s+(\d+)\s*([^\s\d.]*)', sec['header'])
    else:
        first = sec['lines'][0] if sec['lines'] else ''
        m = re.match(r'\[?(\d+)\s*([Α-ΩA-Z]{0,3})\s*[.\-]', first)
    if not m:
        return None
    return int(m.group(1)), m.group(2)


def unit_key(num: tuple[int, str]) -> str:
    n, suf = num
    k = suffix_key(suf)
    return f'art-{n:03d}' + (f'-{k}' if k else '')


def unit_label(num: tuple[int, str], act: dict) -> str:
    n, suf = num
    return f'{act["unit_word"]} {n}{suf.translate(LATIN_LOOK)}'


# ---------------------------------------------------------------- the Gazette

MONTHS = {'ιανουαρ': 1, 'φεβρουαρ': 2, 'μαρτ': 3, 'απριλ': 4, 'μαι': 5, 'μαΐ': 5, 'ιουν': 6, 'ιουλ': 7,
          'αυγουστ': 8, 'σεπτεμβρ': 9, 'οκτωβρ': 10, 'νοεμβρ': 11, 'δεκεμβρ': 12}


def strip_accents(s: str) -> str:
    import unicodedata
    return ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')


def pdf_text(raw: bytes, pages: int = 2) -> str:
    doc = fitz.open(stream=raw, filetype='pdf')
    return '\n'.join(doc[i].get_text() for i in range(min(pages, doc.page_count)))


def gazette(raw: bytes) -> dict | None:
    """Issue number and publication date from the first page of a Gazette extract (its own text layer)."""
    t = pdf_text(raw, 1)
    flat = re.sub(r'\s+', ' ', t)
    # Latin look-alikes in the text layer ('Tρίτη', 'Μαḯου') read as Greek for matching only.
    low = strip_accents(flat.lower()).translate(str.maketrans('aeiotkmnpxyb', 'αειοτκμνρχυβ'))
    # Letter-spaced typesetting in older extracts: 'Ά ρ . 1166' and 'Μ Α Ι Ο Υ 1997'.
    low = re.sub(r'\b([α-ω]) (?=[α-ω]\b)', r'\1', low)
    low = re.sub(r'\b([α-ω]) (?=[α-ω]\b)', r'\1', low)
    low = re.sub(r'\bαρ \.', 'αρ.', low)
    # "Αριθμός 4878 Παρασκευή, 11 Μαρτίου 2022" or "Αρ. 2419 της 17ης ΙΟΥΝΙΟΥ 1989"
    m = re.search(r'(?:αριθμος|αρ\.)\s*(\d{3,5})\s*(?:,\s*)?(?:της\s+)?(?:[α-ω]+\s*,\s*)?(\d{1,2})(?:ης|η)?\s+'
                  r'([α-ω]+)\s+(\d{4})', low)
    if m:
        mon = next((v for k, v in MONTHS.items() if m.group(3).startswith(strip_accents(k))), None)
        if mon:
            return {'issue': m.group(1), 'date': f'{int(m.group(4)):04d}-{mon:02d}-{int(m.group(2)):02d}',
                    'evidence': flat[m.start():m.end()][:160]}
    # "Αρ. 3102, 29.11.96" / "Αρ. 3102, 29.11.1996"
    m = re.search(r'(?:αριθμος|αρ\.)\s*(\d{3,5})\s*,?\s*(\d{1,2})\.(\d{1,2})\.(\d{4}|\d{2})\b', low)
    if m:
        y = int(m.group(4))
        y = y if y > 1000 else (1900 + y if y >= 60 else 2000 + y)
        return {'issue': m.group(1), 'date': f'{y:04d}-{int(m.group(3)):02d}-{int(m.group(2)):02d}',
                'evidence': flat[m.start():m.end()][:160]}
    return None


# ---------------------------------------------------------------- acts

ACTS = {
    '2018_1_125': {
        'part': '10-data-protection', 'slug': 'prostasia-dedomenon', 'short': 'N.125(I)/2018',
        'title': 'Ο περί της Προστασίας των Φυσικών Προσώπων Έναντι της Επεξεργασίας των Δεδομένων Προσωπικού '
                 'Χαρακτήρα και της Ελεύθερης Κυκλοφορίας των Δεδομένων αυτών Νόμος του 2018',
        'numbered_by': 'text', 'unit_word': 'Άρθρο', 'base': '125(I)/2018', 'preamble': True,
    },
    'syntagma': {
        'part': '20-constitution', 'slug': 'syntagma', 'short': 'Σύνταγμα',
        'title': 'Το Σύνταγμα της Κυπριακής Δημοκρατίας', 'numbered_by': 'header', 'unit_word': 'Άρθρο',
        'base': 'ΣΥΝΤΑΓΜΑ', 'preamble': False,
    },
    '0_154': {
        'part': '30-criminal-code', 'slug': 'poinikos-kodikas', 'short': 'ΚΕΦ.154',
        'title': 'Ο περί Ποινικού Κώδικα Νόμος (ΚΕΦ.154)', 'numbered_by': 'text', 'unit_word': 'Άρθρο',
        'base': 'ΚΕΦ.154', 'preamble': False,
    },
}


def law_key(label: str) -> str:
    m = re.fullmatch(r'(\d+)(\(I+\))?/(\d{4})', label)
    if m:
        return f'n-{m.group(3)}-{int(m.group(1)):03d}' + ('-i' if m.group(2) else '')
    return {'ΣΥΝΤΑΓΜΑ': 'syntagma-1960', 'ΚΕΦ.154': 'kef-154'}.get(label) or \
        'anak-' + re.sub(r'\D', '', label)


def load_act(code: str, pins: dict) -> dict:
    p = pins[code]
    fulls = []
    for f in p['full']:
        raw = read(f['ts'], f['url'])
        if raw:
            fulls.append({'ts': f['ts'], 'url': f['url'], 'raw': raw, 'page': parse_page(raw)})
    old = {}
    for link, c in p['old'].items():
        raw = read(c['ts'], c['url'])
        if raw:
            old[link] = {'ts': c['ts'], 'url': c['url'], 'raw': raw, 'page': parse_page(raw)}
    return {'fulls': fulls, 'old': old, 'pins': p}


# ---------------------------------------------------------------- composing versions

def unit_text(header: str, lines: list[str]) -> str:
    return '\n'.join(([f'# {header}'] if header else []) + lines) + '\n'


def compose(code: str, data: dict) -> dict:
    """Every version CyLaw's histories imply, built where every section's wording is archived."""
    A = ACTS[code]
    latest = data['fulls'][-1]
    order = latest['page']['instruments']
    idx = {lab: i for i, lab in enumerate(order)}
    secs = latest['page']['sections']
    report = {'order': order, 'latest': latest['ts'], 'unknown_labels': [], 'disagree': [], 'dropped_ids': [],
              'versions': [], 'full_checks': []}
    hist_idx = {}
    for s in secs:
        hi = []
        for lab, _ in s['hist']:
            if lab in idx:
                hi.append(idx[lab])
            else:
                report['unknown_labels'].append((s['id'], lab))
        hist_idx[s['id']] = sorted(set(hi))

    def eff(sid: str, k: int) -> int | None:
        got = [i for i in hist_idx[sid] if i <= k]
        return got[-1] if got else None

    texts: dict[tuple[str, int], list[tuple[str, str, str]]] = {}

    def add(sid, e, src, sec):
        texts.setdefault((sid, e), []).append((src, wb_url(*src.split('|', 1)), unit_text(sec['header'], sec['lines'])))

    for s in secs:
        if hist_idx[s['id']]:
            add(s['id'], hist_idx[s['id']][-1], f'{latest["ts"]}|{latest["url"]}', s)
        for lab, href in s['hist']:
            if href and not href.endswith(f'{s["id"]}.html') and href in data['old'] and lab in idx:
                o = data['old'][href]
                osecs = [x for x in o['page']['sections'] if x['id'] == s['id']]
                if osecs:
                    add(s['id'], idx[lab], f'{o["ts"]}|{o["url"]}', osecs[0])
    keys = {}
    for s in secs:
        num = section_number(A, s)
        if num is None:
            raise SystemExit(f'{code}: no section number for {s["id"]} {s["header"]!r} {s["lines"][:1]}')
        k = unit_key(num)
        if k in {v[0] for v in keys.values()}:
            raise SystemExit(f'{code}: duplicate unit key {k}')
        keys[s['id']] = (k, unit_label(num, A))
    sid_of_key = {k: sid for sid, (k, _) in keys.items()}

    by_id = {s['id']: s for s in secs}
    fulls_k = []
    aliases = {}  # per full copy: its section id -> the newest page's section id
    for f in reversed(data['fulls']):
        ins = f['page']['instruments']
        if not ins or ins[-1] not in idx:
            report['unknown_labels'].append((f['ts'], ins[-1] if ins else None))
            continue
        L = idx[ins[-1]]
        fulls_k.append((f, L))
        ids_here = {t['id'] for t in f['page']['sections']}
        amap = aliases.setdefault(f['ts'], {})
        for t in f['page']['sections']:
            sid = t['id']
            if sid not in by_id:
                # CyLaw sometimes re-creates a section under a new id (arts. 145, 252, 253 of Cap. 154): an older
                # copy's section is the same provision when its number matches a section of the newest page that
                # this copy does not also hold under the new id.
                num = section_number(A, t) if t['lines'] else None
                new = sid_of_key.get(unit_key(num)) if num else None
                if new and new not in ids_here:
                    amap[sid] = new
                    sid = new
                else:
                    report['dropped_ids'].append((f['ts'], t['id'], t['header'], (t['lines'] or [''])[0][:60]))
                    continue
            e = eff(sid, L)
            if e is not None:
                add(sid, e, f'{f["ts"]}|{f["url"]}', t)

    # Preamble and annexes carry no history on CyLaw: kept only if every archived full copy has the same text.
    fixed = {}
    if A['preamble']:
        pres = {tuple(f['page']['preamble'] or []) for f in data['fulls']}
        if len(pres) == 1 and next(iter(pres)):
            fixed['preamble'] = {'label': 'Προοίμιο', 'kind': 'preamble',
                                 'text': unit_text('Προοίμιο', list(next(iter(pres))))}
        else:
            report['preamble_varies'] = len(pres)
    annex_sets = {tuple((a['title'], tuple(a['lines'])) for a in f['page']['annexes']) for f in data['fulls']}
    if len(annex_sets) == 1:
        for i, (title, lines) in enumerate(next(iter(annex_sets)), 1):
            fixed[f'annex-{i:02d}'] = {'label': title, 'kind': 'annex', 'text': unit_text(title, list(lines))}
    else:
        report['annexes_vary'] = sorted(len(a) for a in annex_sets)

    versions = []
    for k in range(len(order)):
        units, srcs, missing = {}, {}, []
        for s in secs:
            e = eff(s['id'], k)
            if e is None:
                continue
            cands = texts.get((s['id'], e))
            if not cands:
                missing.append(f'{keys[s["id"]][1]} as left by {order[e]}')
                continue
            src, url, text = cands[0]
            for src2, _, text2 in cands[1:]:
                if text2 != text:
                    report['disagree'].append((keys[s['id']][0], order[e], src.split('|')[0], src2.split('|')[0]))
            key, label = keys[s['id']]
            units[key] = {'label': label, 'kind': 'art', 'text': text}
            srcs[key] = url
        units.update(fixed)
        versions.append({'k': k, 'law': order[k], 'units': dict(sorted(units.items())), 'srcs': srcs,
                         'missing': missing})

    # Check: each archived full copy against the version rebuilt for its amendment list.
    for f, L in fulls_k:
        v = versions[L]
        got = {}
        for t in f['page']['sections']:
            sid = aliases.get(f['ts'], {}).get(t['id'], t['id'])
            if sid in keys:
                got[keys[sid][0]] = unit_text(t['header'], t['lines'])
        want = {k: u['text'] for k, u in v['units'].items() if u['kind'] == 'art'}
        diff = sorted(k for k in set(got) | set(want) if got.get(k) != want.get(k))
        report['full_checks'].append({'ts': f['ts'], 'last': order[L], 'complete': not v['missing'],
                                      'differ': diff})
    report['versions'] = [{'law': v['law'], 'units': len(v['units']), 'missing': v['missing']} for v in versions]
    return {'versions': versions, 'report': report, 'keys': keys, 'hist_idx': hist_idx, 'order': order,
            'secs': secs, 'texts': texts, 'fixed': fixed}


# ---------------------------------------------------------------- laws and dates

# Laws whose own text sets a commencement other than publication: label -> (in-force day, the law's words).
# Each was read in the law's Gazette PDF text layer (or, where noted, CyLaw's note quoting the law).
COMMENCEMENT: dict[str, tuple[str, str]] = {
    '95/1989': ('1990-01-01', 'its s. 5: «Η ισχύς του παρόντα Νόμου αρχίζει την 1.1.1990.»'),
    '67(I)/2025': ('2027-07-01', 'its s. 3: «Ο παρών Νόμος τίθεται σε ισχύ την 1η Ιουλίου 2027.»'),
    '134(I)/2020': ('2020-10-01', 'its s. 3: «Οι διατάξεις του παρόντος Νόμου τίθενται σε ισχύ την 1η Οκτωβρίου '
                                  '2020.»'),
}

# Laws whose commencement is partly deferred to an event another law fixes; dated by publication, said so.
DEFERRED = {
    '103(I)/2022': 'its s. 7 brings it into force on publication, except Art. 144 para. 1(3) and (4) (from the day '
                   'the Supreme Court begins to sit as Supreme Constitutional Court and Supreme Court) and the repeal '
                   'of Art. 155(2) (from the day the Court of Appeal begins to exercise jurisdiction, as a law '
                   'provides); those days are not in our sources, so these changes show from publication',
}

# Base acts: label -> (in-force day, evidence), only where a source gives it.
BASE_DATES: dict[str, tuple[str, str]] = {}

LAW_KIND = {}  # label -> kind, where not 'law'


def law_title(raw: bytes) -> str | None:
    flat = re.sub(r'\s+', ' ', pdf_text(raw, 1))
    m = re.search(r'([ΟO] περί .{5,300}? Νόμος του \d{4}) εκδίδεται', flat)
    return m.group(1).replace('O περί', 'Ο περί') if m else None


def law_label(label: str) -> str:
    return {'ΣΥΝΤΑΓΜΑ': 'Σύνταγμα της Κυπριακής Δημοκρατίας (1960)', 'ΚΕΦ.154': 'ΚΕΦ.154'}.get(label) or \
        (f'Ν. {label}' if re.fullmatch(r'\d+(\(I+\))?/\d{4}', label) else label)


def direct_read(url: str) -> bytes | None:
    p = CACHE / hashlib.sha256(url.encode('utf-8')).hexdigest()
    return p.read_bytes() if p.exists() else None


def date_laws(code: str, order: list[str], pins: dict) -> dict:
    out = {}
    gaz = {norm_label(k): v for k, v in pins[code]['gazette'].items()}
    gpo = pins[code].get('gpo', {})
    for i, lab in enumerate(order):
        g = gaz.get(lab)
        raw = read(g['ts'], g['url']) if g else None
        gz = gazette(raw) if raw else None
        title = law_title(raw) if raw else None
        if not gz and lab in gpo:
            # The Gazette issue itself, from the Printing Office's archive: its first-page header gives the date,
            # and fetch.py confirmed the law's own heading ("Αριθμός N(Ι) του Y") is in the issue.
            h = gpo[lab]
            iraw = direct_read(h['pdf'])
            gz = gazette(iraw) if iraw else None
            if gz and gz['date'] != h['date']:
                raise SystemExit(f'{lab}: Gazette header {gz["date"]} != archive listing {h["date"]}')
            if gz:
                gz['source'] = h['pdf']
        info = {'label': law_label(lab), 'title': title, 'kind': LAW_KIND.get(lab, 'law'),
                'published': gz['date'] if gz else None, 'issue': gz['issue'] if gz else None,
                'evidence': gz['evidence'] if gz else None,
                'url': (gz or {}).get('source') or (
                    ('https://www.cylaw.org' + re.sub(r'^https?://[^/]+', '', g['url'])) if g else None),
                'archive': wb_url(g['ts'], g['url']) if g else None}
        if lab in COMMENCEMENT:
            info['in_force'], info['commencement'] = COMMENCEMENT[lab]
        elif lab in BASE_DATES:
            info['in_force'], info['commencement'] = BASE_DATES[lab]
        else:
            info['in_force'] = info['published']
        out[lab] = info
    return out


COUNTRY = {
    'code': 'CY', 'name': 'Cyprus', 'slug': 'cyprus', 'lang': 'el', 'tz': 'Asia/Nicosia', 'future_branch': 'mellon',
    'publisher': {'name': 'CyLaw (Cyprus Bar Association, KINOP)', 'email': 'cylaw@cylaw.invalid'},
    'default_in_force_rule': None,  # filled from Cap. 1 in main()
    'licence_note': 'Πηγή: CyLaw (https://www.cylaw.org), Παγκύπριος Δικηγορικός Σύλλογος / ΚΙΝΟΠ. Source: CyLaw '
                    '(https://www.cylaw.org), the Cyprus Bar Association\'s legal information service run by KINOP; '
                    'read from Internet Archive copies.',
}


def in_force_states(C: dict, laws: dict) -> list[dict]:
    """The act on each in-force day. CyLaw's list is in publication order, but a law may take effect later than
    the next one (95/1989 on 1.1.1990; 67(I)/2025 on 1.7.2027), so states are made from the set of laws in force
    on each day: a section reads as left by the last of its instruments in force, provided every earlier
    instrument of that section is in force too (otherwise CyLaw's wording cannot be split and the day is left out).
    A law without a sourced in-force day makes every day from the publication of the law before it unbuildable."""
    order, n = C['order'], len(C['order'])
    days = [laws[lab].get('in_force') for lab in order]
    pubs = [laws[lab].get('published') for lab in order]
    # A law with no sourced day was published between its neighbours in CyLaw's list (which is in publication
    # order): it is certainly in force from the next dated law's publication, and unknown before that from the
    # previous one's. States in that window are left out; later states include it.
    window = {}
    for i in range(1, n):
        if days[i] is None:
            lo = next((pubs[j] for j in range(i - 1, -1, -1) if pubs[j]), None)
            hi = next((pubs[j] for j in range(i + 1, n) if pubs[j]), None)
            window[i] = (lo or '0000-00-00', hi or '9999-99-99')
    states = []
    for D in sorted({d for d in days if d}):
        S = {0} | {i for i in range(n) if (days[i] and days[i] <= D) or (i in window and D >= window[i][1])}
        units, srcs, missing, eff = {}, {}, [], {}
        for i, (lo, hi) in window.items():
            if lo <= D < hi:
                missing.append(f'{order[i]} has no sourced in-force day and may already be in force')
        for s in C['secs']:
            chain = C['hist_idx'][s['id']]
            inf = [i for i in chain if i in S]
            if inf != chain[:len(inf)]:
                missing.append(f'{C["keys"][s["id"]][1]}: {", ".join(order[i] for i in chain if i not in S)} '
                               f'not yet in force but CyLaw\'s wording includes it')
                continue
            if not inf:
                continue
            e = inf[-1]
            eff[s['id']] = e
            cands = C['texts'].get((s['id'], e))
            if not cands:
                missing.append(f'{C["keys"][s["id"]][1]} as left by {order[e]}')
                continue
            key, label = C['keys'][s['id']]
            units[key] = {'label': label, 'kind': 'art', 'text': cands[0][2]}
            srcs[key] = cands[0][1]
        units.update(C['fixed'])
        states.append({'from': D, 'laws': sorted(i for i in S if days[i] == D), 'S': S, 'eff': eff,
                       'units': dict(sorted(units.items())), 'srcs': srcs, 'missing': missing})
    return states


def sha_of(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def build_part(code: str, pins: dict, rule: dict) -> tuple[dict, dict]:
    A = ACTS[code]
    data = load_act(code, pins)
    C = compose(code, data)
    order = C['order']
    info = date_laws(code, order, pins)
    states = in_force_states(C, info)
    report = C['report']
    # The history starts at the first state after which no state is missing.
    start = len(states)
    while start > 0 and not states[start - 1]['missing']:
        start -= 1
    left_out = [{'from': s['from'], 'laws': [order[i] for i in s['laws']], 'missing': s['missing'][:20],
                 'missing_count': len(s['missing'])} for s in states[:start]]
    built = states[start:]
    laws, versions = {}, []
    latest = data['fulls'][-1]
    full_by_last = {}
    for f in data['fulls']:
        ins = f['page']['instruments']
        if ins:
            full_by_last[ins[-1]] = f  # newest copy whose list ends at that law
    prev, prev_S = None, set()
    for j, st in enumerate(built):
        credits = {}
        if prev is not None:
            for key in sorted(set(prev['units']) | set(st['units'])):
                if prev['units'].get(key) == st['units'].get(key):
                    continue
                sid = next((s for s, (k, _) in C['keys'].items() if k == key), None)
                new = [order[i] for i in C['hist_idx'].get(sid, []) if i in st['S'] and i not in prev_S]
                if new:
                    credits[key] = [law_key(l) for l in new]
                else:
                    report.setdefault('uncredited', []).append((st['from'], key))
        lab_last = order[max(st['laws'])]
        f = full_by_last.get(lab_last) if lab_last == order[max(st['S'])] else None
        f = f or latest
        n_ln = sum(1 for k, u in st['srcs'].items() if '/nomoi/enop/ind/' in u)
        n_full = sum(1 for k, u in st['srcs'].items() if '-ln' not in u and latest['ts'] not in u)
        v = {'from': st['from'], 'source_url': wb_url(f['ts'], f['url']), 'sha256': sha_of(f['raw'])}
        if j == 0:
            v['units'] = st['units']
        else:
            ch = {k: st['units'].get(k) for k in credits}
            for k in set(prev['units']) ^ set(st['units']):
                ch.setdefault(k, st['units'].get(k))
            for k in set(prev['units']) & set(st['units']):
                if prev['units'][k] != st['units'][k]:
                    ch.setdefault(k, st['units'][k])
            v['changes'] = dict(sorted(ch.items()))
            v['credits'] = credits
        v['note'] = (f'Rebuilt from CyLaw\'s per-section amendment histories: {n_ln} provisions from archived '
                     f'old-wording pages, {n_full} from archived full copies of earlier dates, the rest from the '
                     f'newest archived consolidated text ({latest["ts"][:8]}).')
        if j and not v['changes']:
            report.setdefault('no_change', []).append([order[i] for i in st['laws']])
            continue
        versions.append(v)
        prev, prev_S = st, st['S']
    used = {l for v in versions for ls in v.get('credits', {}).values() for l in ls}
    first_law = None
    earlier = []
    if start == 0 and info[order[0]].get('in_force'):
        first_law = law_key(order[0])
    else:
        first_in = built[0]['S'] if built else set()
        earlier = [law_key(order[i]) for i in sorted(first_in)]
    for lab in order:
        k = law_key(lab)
        if k in used or k == first_law or k in earlier:
            i = info[lab]
            note = None
            if i.get('commencement'):
                note = None  # stated in decisions
            laws[k] = {'label': i['label'], 'title': i['title'], 'kind': i['kind'], 'enacted': None,
                       'published': i['published'], 'url': i['url'], 'temporary_until': None, 'restores': None,
                       'note': note}
    act = {'slug': A['slug'], 'short': A['short'], 'title': A['title'],
           'url': f'https://www.cylaw.org/nomoi/enop/non-ind/{code}/full.html',
           'first_law': first_law, 'earlier_laws': earlier, 'versions': versions}
    decisions = [
        f'{A["short"]}: versions rebuilt from CyLaw\'s per-section amendment histories (newest archived consolidated '
        f'page {latest["ts"]}, {len(data["old"])} archived old-wording pages, {len(data["fulls"])} archived full '
        f'copies); each version is the act on the in-force day of the laws CyLaw lists, every section as left by '
        f'its last instrument in force that day.',
    ]
    for lab in order:
        i = info[lab]
        if i.get('commencement'):
            decisions.append(f'{A["short"]}: {i["label"]} takes effect on {i["in_force"]}, not on publication '
                             f'({i["published"]}): {i["commencement"]}')
        if lab in DEFERRED:
            decisions.append(f'{A["short"]}: {i["label"]} is dated by its publication ({i["published"]}), but '
                             f'{DEFERRED[lab]}.')
        if i['url'] and 'mof.gov.cy' in i['url']:
            decisions.append(f'{A["short"]}: {i["label"]} is dated from the Gazette issue itself (Αρ. {i["issue"]}, '
                             f'{i["published"]}) in the Government Printing Office archive, because CyLaw\'s extract '
                             f'is not archived or has no Gazette header; the issue holds the law\'s own heading.')
    dis = sorted({(a, b) for a, b, _, _ in report['disagree']})
    if dis:
        decisions.append(f'{A["short"]}: where archived copies disagree on a section\'s wording under the same law, the '
                         f'newest CyLaw page is used (CyLaw later corrected its transcription, or consolidated the '
                         f'law some months after it was published): ' +
                         ', '.join(f'{k} as left by {l}' for k, l in dis) + '.')
    decisions.append(f'{A["short"]}: typesetting normalised in every source alike: NBSP and tabs to spaces, curly '
                     f'quotes and dashes to plain ones, micro/increment signs to Greek μ/Δ, and Latin look-alike '
                     f'letters inside Greek words to Greek; Part headings, CyLaw\'s notes (Σημείωση) and footnotes '
                     f'are left out; the preamble and annexes, which carry no history on CyLaw, are kept only where '
                     f'every archived full copy has the same text.')
    if left_out:
        decisions.append(f'{A["short"]}: {len(left_out)} earlier version(s) left out because a section\'s wording '
                         f'or a law\'s in-force day is not archived; the history starts at {built[0]["from"] if built else "-"}: ' +
                         '; '.join(f'{x["from"]} ({", ".join(x["laws"]) or "-"}): '
                                   + (x['missing'][0] if x['missing'] else 'complete, but a later day is missing, '
                                      'so its changes could not be dated')
                                   + (f' (+{x["missing_count"] - 1} more)' if x['missing_count'] > 1 else '')
                                   for x in left_out))
    undated = [lab for lab in order if not info[lab].get('in_force')]
    if undated:
        decisions.append(f'{A["short"]}: no sourced in-force day for: {", ".join(undated)}.')
    part = {'country': dict(COUNTRY, default_in_force_rule=rule), 'acts': [act], 'laws': laws,
            'decisions': decisions}
    report['left_out'] = left_out
    report['built'] = [(v['from'], sorted({l for ls in v.get('credits', {}).values() for l in ls})) for v in versions]
    report['undated'] = undated
    report['dates'] = {lab: (info[lab]['published'], info[lab].get('in_force')) for lab in order}
    return part, report


def cap1_rule(pins: dict) -> dict:
    c = pins['cap1']
    pg = parse_page(read(c['ts'], c['url']))
    s7 = next(s for s in pg['sections'] if s['lines'] and s['lines'][0].startswith('7. '))
    return {'text': 'Ο περί Ερμηνείας Νόμος (ΚΕΦ.1), άρθρο 7: «' + s7['lines'][0][3:] + '» (Interpretation Law, '
                    'Cap. 1, s. 7: every law takes effect on the date of its publication in the Official Gazette '
                    'unless it provides otherwise.) Each amending law is dated by its Gazette issue, read from the '
                    'Gazette extract\'s own text layer; a law\'s own commencement clause overrides this.',
            'source': wb_url(c['ts'], c['url'])}


def requests_count() -> int:
    p = CACHE / 'requests.jsonl'
    return sum(1 for _ in p.open(encoding='utf-8')) if p.exists() else 0


def main(argv: list[str]) -> None:
    pins = json.loads((HERE / 'sources.json').read_text(encoding='utf-8'))
    rule = cap1_rule(pins)
    codes = [a for a in argv if not a.startswith('--')] or list(ACTS)
    PARTS.mkdir(exist_ok=True)
    for code in codes:
        part, report = build_part(code, pins, rule)
        part['sources'] = [{
            'name': 'CyLaw (cylaw.org), through the Internet Archive', 'url': 'https://www.cylaw.org',
            'retrieved': RETRIEVED, 'requests': requests_count(),
            'licence': 'CyLaw terms of use (cylaw.org/terms.html): legislation on the site may be copied, printed '
                       'and used free of charge provided CyLaw is identified as the source; bulk or automated '
                       'downloading from the site needs KINOP\'s prior written consent, so every page was read from '
                       'an Internet Archive copy instead.',
            'notes': f'{ACTS[code]["short"]}: consolidated page /nomoi/enop/non-ind/{code}/full.html (archived copies '
                     f'pinned in tools/sources.json), per-section old-wording pages /nomoi/enop/ind/{code}/, and the '
                     f'Official Gazette extracts /nomoi/arith/*.pdf (text layer only, no OCR).'}]
        part['ai_use'] = ['none: parse.py is deterministic code; no model wrote or read legal text.']
        out = PARTS / f'{ACTS[code]["part"]}.json'
        tmp = out.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(part, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8',
                       newline='\n')
        tmp.replace(out)
        if '--report' in argv:
            r = {k: v for k, v in report.items() if k not in ('disagree',)}
            r['disagree'] = sorted({(a, b) for a, b, c, d in report['disagree']})
            print(json.dumps({code: r}, ensure_ascii=False, indent=1)[:12000])
        n = len(part['acts'][0]['versions'])
        print(f'{code}: {n} versions -> {out.name}', file=sys.stderr)


if __name__ == '__main__':
    main(sys.argv[1:])

