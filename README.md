# Cyprus: law history in git

The law of Cyprus as a git history: one file per provision, one commit per law on the day it took effect, and the law that made each change as the commit's author. `git blame` names the law behind every paragraph; `git log` lists every change to a provision; `tools/on.py` gives the text in force on any day.

It follows the shared design of [lexifina/global-law](https://github.com/lexifina/global-law), which places it at `cy/`. The texts are in Greek, the official language in which CyLaw publishes them.

**What is in it now**

| Folder | Act | Versions | History |
| --- | --- | ---: | --- |
| `syntagma/` | The Constitution of the Republic of Cyprus (Το Σύνταγμα της Κυπριακής Δημοκρατίας) | 15 | 2013-07-17 to 2025-11-07, and 2027-07-01 on `mellon` |
| `poinikos-kodikas/` | The Criminal Code, Cap. 154 (Ο περί Ποινικού Κώδικα Νόμος, ΚΕΦ.154) | 15 | 2017-04-07 to 2025-12-12 |
| `poiniki-dikonomia/` | The Criminal Procedure Law, Cap. 155 (Ο περί Ποινικής Δικονομίας Νόμος, ΚΕΦ.155) | 10 | 2014-02-21 to 2025-12-19 |
| `astika-adikimata/` | The Civil Wrongs Law, Cap. 148 (Ο περί Αστικών Αδικημάτων Νόμος, ΚΕΦ.148) | 1 | 2012-05-31 (the text as last amended, by 66(I)/2012) |
| `etaireies/` | The Companies Law, Cap. 113 (Ο περί Εταιρειών Νόμος, ΚΕΦ.113) | 1 | 2026-02-06 (the text as last amended, by 2(I)/2026) |
| `politiki-dikonomia/` | The Civil Procedure Law, Cap. 6 (Ο περί Πολιτικής Δικονομίας Νόμος, ΚΕΦ.6) | 8 | 2014-05-23 to 2025-07-22 |
| `dikastiria-14-1960/` | The Courts of Justice Law 14/1960 (Ο περί Δικαστηρίων Νόμος του 1960) | 8 | 2022-06-02 to 2026-05-12 |
| `archeio-plithysmou/` | The Civil Registry Law 141(I)/2002 (Ο περί Αρχείου Πληθυσμού Νόμος του 2002) | 16 | 2013-12-27 to 2025-12-12 |
| `xenodocheia/` | The Hotels and Tourist Accommodation Law 34(I)/2019 | 9 | 2019-03-15 (as enacted) to 2025-10-24 |
| `dimoi/` | The Municipalities Law 52(I)/2022 (Ο περί Δήμων Νόμος του 2022) | 1 | 2025-10-17 (the text as last amended, by 177(I)/2025) |
| `prostasia-dedomenon/` | Law 125(I)/2018 on the protection of natural persons with regard to the processing of personal data (the GDPR implementing law) | 2 | 2018-07-31 (as enacted) to 2022-03-11 |

Each act folder has a README listing its versions.

## Sources

- **CyLaw** (cylaw.org), the Cyprus Bar Association's legal information service run by KINOP, publishes each act consolidated. Under every section it lists the laws that made or amended it, oldest first, and links each to the section's wording as that law left it. So the act on any day is rebuilt section by section: each section reads as left by the last of its laws in force that day.
- CyLaw's terms allow free copying with CyLaw named as the source, but bulk or automated downloading from the site needs its written consent. So **no page was fetched from cylaw.org**: every CyLaw page and PDF is an Internet Archive copy, pinned by capture time in `tools/sources.json`.
- The newest archived consolidated page gives today's text. Older wordings come from archived per-section pages and from archived copies of the whole consolidated page made in earlier years (21 for the Constitution since 2013, 27 for Cap. 154 since 2012, 3 for Law 125(I)/2018, 4 for Cap. 155 since 2022, 2 for Cap. 148, 3 for Cap. 113, 4 for Cap. 6).
- **Dates** come from the Official Gazette (Επίσημη Εφημερίδα της Δημοκρατίας). For most laws, the Gazette extract CyLaw files (`/nomoi/arith/<year>_1_<number>.pdf`, archived copy) gives the issue number and date in its own text layer. For 186(I)/2025 and 212(I)/2025, whose extracts are not archived, the Gazette issue itself was read from the Government Printing Office's archive (mof.gov.cy/gpo). No OCR is done.

## What is missing

- **Constitution before 2013-07-17.** The 1960 text and the versions of 1990-01-01 (95/1989), 1996 (106(I)/1996, 115(I)/1996) and 2002 (104(I)/2002) are complete on CyLaw, but they are left out because their dates cannot be sourced:
  - our sources do not state the day the 1960 Constitution took effect;
  - for 127(I)/2006 and 51(I)/2010, CyLaw's PDFs are retyped texts without the Gazette header, and the Printing Office's online archive has no laws annex for those years. Without them, changes made between 2002 and 2013 cannot be dated, so the history starts with the version in force after 68(I)/2013, credited to CyLaw as the oldest version available.
- **Constitution, 103(I)/2022.** Its s. 7 brings it into force on publication, except for Art. 144 para. 1(3) and (4) and the repeal of Art. 155(2), which start when the courts concerned begin to sit, as other laws provide. Those days are not in our sources, so these changes show from publication (2022-07-12).
- **Cap. 154 before 2017-04-07.** CyLaw lists 85 amending instruments since 1962. 36 of them (five from 1962–1965, 29 from 1999–2012, and 43(I)/2016) and one notice (ΑΝΑΚ.3309) have no sourced date: most of CyLaw's PDFs for them are retypes without the Gazette header, the 1962–1965 extracts' text layers show no date, 43(I)/2016's PDF has an unreadable text layer, and the Printing Office's online archive has no laws annex for those years. The history therefore starts with the version in force after 31(I)/2017, as the oldest version available.
- **Cap. 155 before 2014-02-21.** CyLaw lists 33 amending instruments since 1972. 13 of them (the original text, 93/1972, ΑΝΑΚ.3374, and every law from 14(I)/2001 to 23(I)/2013) have no sourced date: CyLaw's PDFs for them are retypes without the Gazette header and the Printing Office's online archive has no laws annex for those years; and 22 sections' original wording is not archived. The history therefore starts with the version in force after 16(I)/2014. 235(I)/2025 is dated from its Gazette issue (Αρ. 5067, 19.12.2025). CyLaw keeps the deleted earlier sections 92, 93, 94 and 155 ("[Διαγράφηκε]") beside the later sections of the same numbers; the deleted ones are left out.
- **Cap. 148 before 2012-05-31.** Five of its amending laws and a notice (154(I)/2002, 129(I)/2006, 171(I)/2006, 82(I)/2008, ΑΝΑΚ.3309) have no sourced date, so only the text as last amended, by 66(I)/2012, is given, as the oldest version available.
- **Cap. 113 before 2026-02-06.** Most of the laws CyLaw lists from 2000 to 2021 have no sourced date (retyped extracts, no laws annex online for those years), and the wording of s. 2 as left by 162(I)/2025 is not archived, so only the text as last amended, by 2(I)/2026 (Gazette Αρ. 5071, 6.2.2026), is given, as the oldest version available. CyLaw prints ss. 157ΙΑ-157ΙΔ twice with the same text; one copy is used.
- **Cap. 6 before 2014-05-23.** The original text, 14/1960, 11/1965, ΑΝΑΚ.3374, 58(I)/2003, 66(I)/2004 and 138(I)/2006 have no sourced date, so the history starts after the next dated law.
- **Law 14/1960 before 2022-06-02, Law 141(I)/2002 before 2013-12-27 and Law 52(I)/2022 before 2025-10-17.** Earlier versions need Gazette days the online sources do not give (most laws of 1960-2021) or old wordings neither archive holds (s. 22Β of Law 14/1960; 32 sections of Law 52(I)/2022), so the histories start later. Law 34(I)/2019 is complete from its enactment.
- Part headings, CyLaw's editorial notes (Σημείωση) and footnotes quoting transitional provisions of amending laws are left out.

## Dates

- Each commit is dated at **noon, Asia/Nicosia, on the day the change took effect**; the day is also in the `In-force:` trailer, which the tools read.
- Under the Interpretation Law, Cap. 1, s. 7, a law takes effect on the day of its publication in the Official Gazette unless it provides otherwise. Each law is dated by its Gazette issue. Where a law sets its own commencement in its Gazette text, that day is used and listed in `REPRODUCE.md`: 134(I)/2020 (Cap. 154) from 2020-10-01, and 67(I)/2025 (Constitution, Art. 63) from 2027-07-01.
- Versions that take effect after the build day are on the branch `mellon`. Today that is 67(I)/2025, which CyLaw's consolidated text already shows.
- `--before="YYYY-MM-DD"` alone uses your clock's time of day; use `T23:59:59Z`, or the tool.

## A lawyer's questions as git commands

| Question | Command |
| --- | --- |
| What did Article 146 of the Constitution say on 2016-01-01? | `python tools/on.py 2016-01-01 syntagma art-146` |
| Which law wrote each line? | `git blame poinikos-kodikas/art-145.md` |
| Every change, word by word | `git log -p --word-diff syntagma/art-111.md` |
| Every law in the record, in order | `git log --reverse --format="%ad %an" --date=short main` |
| Everything one law changed | `git show law/<key>` |

## How it is checked

- Every version is read back from git on the day it took effect and on the day before (`tools/check_repo.py`); both must match the corpus. Results are in `REPRODUCE.md`.
- Every archived copy of a consolidated page is compared, section by section, with the version rebuilt from CyLaw's histories for the same list of laws. Law 125(I)/2018: all 3 copies match. Constitution: all 21 copies match, except where CyLaw later corrected its own transcription (missing words in Arts. 111, 124, 139 and 153, in copies up to October 2019) and Art. 135A, which CyLaw added to its consolidation some months after 130(I)/2025. Cap. 154: every copy since June 2013 matches, except one correction in Art. 5 ("196" completed to "1960"). Cap. 155: all 4 copies (2022-2026) match. Cap. 6: all 4 copies (2022-2025) match. Cap. 113: the newest copy (October 2026) matches; the two 2025 copies differ in 13 and 34 sections that CyLaw later corrected or re-consolidated. Cap. 148: the newest copy (July 2026) matches; the 2022 copy differs in CyLaw's transcription of every section. In every such case the newest wording is used.
- The last version of each act equals the newest archived consolidated page, section by section.
- Typesetting is normalised in the same way for every source: spaces, quotes, dashes, the micro and increment signs, and Latin look-alike letters typed inside Greek words (CyLaw itself has corrected many of these over the years).

## Licence

- Source: CyLaw (https://www.cylaw.org), Cyprus Bar Association / KINOP. Free to copy and use with CyLaw named as the source (cylaw.org/terms.html). See `LICENSE`.
- Official Gazette issues from the Government Printing Office of the Republic of Cyprus (www.mof.gov.cy/gpo).
- Archived copies come from the Internet Archive (https://web.archive.org).

## What "author" means

The author of a commit is the law that made the change, with an e-mail address that cannot exist, so `git blame` and `git log --author` name laws. The committer is always Lexifina.

This repository is not legal advice.

## Ελληνικά

Η νομοθεσία της Κύπρου ως ιστορικό git: ένα αρχείο για κάθε άρθρο και ένα commit για κάθε νόμο, την ημέρα που τέθηκε σε ισχύ, με συγγραφέα τον νόμο που έκανε την αλλαγή. Περιλαμβάνει το Σύνταγμα (από 17.7.2013), τον Ποινικό Κώδικα, ΚΕΦ.154 (από 7.4.2017), τον περί Ποινικής Δικονομίας Νόμο, ΚΕΦ.155 (από 21.2.2014), τον περί Αστικών Αδικημάτων Νόμο, ΚΕΦ.148 (το κείμενο μετά τον Ν. 66(I)/2012), τον περί Εταιρειών Νόμο, ΚΕΦ.113 (το κείμενο μετά τον Ν. 2(I)/2026), τον περί Πολιτικής Δικονομίας Νόμο, ΚΕΦ.6 (από 23.5.2014), τον περί Δικαστηρίων Νόμο του 1960 (από 2.6.2022), τον περί Αρχείου Πληθυσμού Νόμο του 2002 (από 27.12.2013), τον περί Ξενοδοχείων και Τουριστικών Καταλυμάτων Νόμο του 2019 (από τη θέσπισή του), τον περί Δήμων Νόμο του 2022 (το κείμενο μετά τον Ν. 177(I)/2025) και τον Νόμο 125(I)/2018 για την προστασία δεδομένων προσωπικού χαρακτήρα. Τα κείμενα προέρχονται από το CyLaw (www.cylaw.org, Παγκύπριος Δικηγορικός Σύλλογος / ΚΙΝΟΠ). Κάθε νόμος χρονολογείται με την ημερομηνία δημοσίευσής του στην Επίσημη Εφημερίδα της Δημοκρατίας (περί Ερμηνείας Νόμος, ΚΕΦ.1, άρθρο 7), εκτός αν ο ίδιος ορίζει διαφορετικά. Παλαιότερες εκδόσεις παραλείπονται όπου η ημερομηνία κάποιου τροποποιητικού νόμου δεν μπορεί να τεκμηριωθεί. Δεν αποτελεί νομική συμβουλή.
