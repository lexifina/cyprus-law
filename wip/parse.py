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
HOMO_ALL = str.maketrans('ABEZHIKMNOPTYXo', 'ΑΒΕΖΗΙΚΜΝΟΡΤΥΧο')
GREEK_CH = re.compile(r'[Ͱ-Ͽἀ-῿]')
LATIN_CH = re.compile(r'[A-Za-z]')
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
            if all(c in 'ABEZHIKMNOPTYXo' for c in LATIN_CH.findall(w)):
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
    return s.replace('Ι', 'I')  # Greek capital iota is used for the Latin "(I)" in some entries


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
    low = strip_accents(flat.lower())
    # "Αριθμός 4878 Παρασκευή, 11 Μαρτίου 2022" or "Αρ. 2419 της 17ης ΙΟΥΝΙΟΥ 1989"
    m = re.search(r'(?:αριθμος|αρ\.)\s*(\d{3,5})\s*(?:,\s*)?(?:της\s+)?(?:[α-ω]+\s*,\s*)?(\d{1,2})(?:ης|η)?\s+'
                  r'([α-ω]+)\s+(\d{4})', low)
    if m:
        mon = next((v for k, v in MONTHS.items() if strip_accents(m.group(3)).startswith(strip_accents(k))), None)
        if mon:
            return {'issue': m.group(1), 'date': f'{int(m.group(4)):04d}-{mon:02d}-{int(m.group(2)):02d}',
                    'evidence': flat[max(0, m.start() - 0):m.end() + 0][:160]}
    m = re.search(r'(?:αριθμος|αρ\.)\s*(\d{3,5})\s*,?\s*(\d{1,2})\.(\d{1,2})\.(\d{4})', low)
    if m:
        return {'issue': m.group(1), 'date': f'{int(m.group(4)):04d}-{int(m.group(3)):02d}-{int(m.group(2)):02d}',
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
            if href and '-ln' in href and href in data['old'] and lab in idx:
                o = data['old'][href]
                osecs = [x for x in o['page']['sections'] if x['id'] == s['id']]
                if osecs:
                    add(s['id'], idx[lab], f'{o["ts"]}|{o["url"]}', osecs[0])
    by_id = {s['id']: s for s in secs}
    fulls_k = []
    for f in reversed(data['fulls']):
        ins = f['page']['instruments']
        if not ins or ins[-1] not in idx:
            report['unknown_labels'].append((f['ts'], ins[-1] if ins else None))
            continue
        L = idx[ins[-1]]
        fulls_k.append((f, L))
        for t in f['page']['sections']:
            if t['id'] not in by_id:
                report['dropped_ids'].append((f['ts'], t['id'], t['header'], (t['lines'] or [''])[0][:60]))
                continue
            e = eff(t['id'], L)
            if e is not None:
                add(t['id'], e, f'{f["ts"]}|{f["url"]}', t)

    keys = {}
    for s in secs:
        num = section_number(A, s)
        if num is None:
            raise SystemExit(f'{code}: no section number for {s["id"]} {s["header"]!r} {s["lines"][:1]}')
        k = unit_key(num)
        if k in keys.values():
            raise SystemExit(f'{code}: duplicate unit key {k}')
        keys[s['id']] = (k, unit_label(num, A))

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
            if t['id'] in keys:
                got[keys[t['id']][0]] = unit_text(t['header'], t['lines'])
        want = {k: u['text'] for k, u in v['units'].items() if u['kind'] == 'art'}
        diff = sorted(k for k in set(got) | set(want) if got.get(k) != want.get(k))
        report['full_checks'].append({'ts': f['ts'], 'last': order[L], 'complete': not v['missing'],
                                      'differ': diff})
    report['versions'] = [{'law': v['law'], 'units': len(v['units']), 'missing': v['missing']} for v in versions]
    return {'versions': versions, 'report': report, 'keys': keys, 'hist_idx': hist_idx, 'order': order,
            'secs': secs}


# ---------------------------------------------------------------- laws and dates

# Laws whose own text sets a commencement other than publication: label -> (in-force day, the law's words).
# Each was read in the law's Gazette PDF text layer (or, where noted, CyLaw's note quoting the law).
COMMENCEMENT: dict[str, tuple[str, str]] = {}

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


def date_laws(code: str, order: list[str], pins: dict) -> dict:
    out = {}
    for i, lab in enumerate(order):
        g = pins[code]['gazette'].get(lab)
        raw = read(g['ts'], g['url']) if g else None
        gz = gazette(raw) if raw else None
        title = law_title(raw) if raw else None
        info = {'label': law_label(lab), 'title': title, 'kind': LAW_KIND.get(lab, 'law'),
                'published': gz['date'] if gz else None, 'issue': gz['issue'] if gz else None,
                'evidence': gz['evidence'] if gz else None,
                'url': ('https://www.cylaw.org' + re.sub(r'^https?://[^/]+', '', g['url'])) if g else None,
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

