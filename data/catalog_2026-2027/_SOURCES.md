# Data sources — catalog pages added on 7 Nov 2026

All files below were cleaned from public pages of the **Bethlehem University Undergraduate Catalog 2026–2027** (reg.bethlehem.edu). Each file starts with its exact source URL. Files whose names start with `_` (like this one) are not indexed by the assistant.

| File | Title | Source |
|---|---|---|
| `data/catalog_2026-2027/programs/computer_simulation_csse/01_program_description.md` | CSSE Program Description — وصف البرنامج | https://reg.bethlehem.edu:100/CaDetails/ProgramDescription.aspx?majorCode=248&page=0&catalogID=46&type=1 |
| `data/catalog_2026-2027/programs/computer_simulation_csse/02_learning_outcomes.md` | CSSE Program Learning Outcomes — مخرجات التعلم | https://reg.bethlehem.edu:100/CaDetails/ProgramDescription.aspx?majorCode=248&page=1&catalogID=46&type=1 |
| `data/catalog_2026-2027/programs/computer_simulation_csse/03_acceptance_to_major.md` | CSSE Criteria of Acceptance to Major — شروط القبول في التخصص | https://reg.bethlehem.edu:100/CaDetails/ProgramDescription.aspx?majorCode=248&page=2&catalogID=46&type=1 |
| `data/catalog_2026-2027/programs/computer_simulation_csse/04_degree_requirements.md` | CSSE Degree Requirements — متطلبات الدرجة وتوزيع الساعات | https://reg.bethlehem.edu:100/CaDetails/ProgramDescription.aspx?majorCode=248&page=3&catalogID=46&type=1 |
| `data/catalog_2026-2027/programs/computer_simulation_csse/05_program_of_study.md` | CSSE Program of Study (All Courses) — قائمة مساقات البرنامج | https://reg.bethlehem.edu:100/CaDetails/ProgramDescription.aspx?majorCode=248&page=4&catalogID=46&type=1 |
| `data/catalog_2026-2027/programs/computer_simulation_csse/06_paradigm.md` | CSSE Paradigm (Semester-by-Semester Study Plan) — الخطة الدراسية حسب الفصول | https://reg.bethlehem.edu:100/CaDetails/ProgramDescription.aspx?majorCode=248&page=5&catalogID=46&type=1 |
| `cleaned_sources/catalog_2026-2027/regulations/01_student_classification.md` | Student Classification — تصنيف الطلبة حسب السنة الدراسية | https://reg.bethlehem.edu:100/Menu/PageDetails.aspx?catalogID=46&PageID=11&type=1 |
| `cleaned_sources/catalog_2026-2027/regulations/02_student_load.md` | Student Load — العبء الدراسي | https://reg.bethlehem.edu:100/Menu/PageDetails.aspx?catalogID=46&PageID=12&type=1 |
| `cleaned_sources/catalog_2026-2027/regulations/03_senior_students_extra_load.md` | Senior Students Extra Load — العبء الإضافي لطلبة السنة الأخيرة | https://reg.bethlehem.edu:100/Menu/PageDetails.aspx?catalogID=46&PageID=13&type=1 |
| `cleaned_sources/catalog_2026-2027/regulations/04_identification.md` | Identification — الرقم والبطاقة الجامعية | https://reg.bethlehem.edu:100/Menu/PageDetails.aspx?catalogID=46&PageID=14&type=1 |
| `cleaned_sources/catalog_2026-2027/regulations/05_degree_requirements_general.md` | Degree Requirements — متطلبات الحصول على درجة البكالوريوس | https://reg.bethlehem.edu:100/Menu/PageDetails.aspx?catalogID=46&PageID=15&type=1 |
| `cleaned_sources/catalog_2026-2027/regulations/06_university_requirements.md` | University Requirements (Core Curriculum) — متطلبات الجامعة | https://reg.bethlehem.edu:100/Menu/PageDetails.aspx?catalogID=46&PageID=16&type=1 |
| `cleaned_sources/catalog_2026-2027/regulations/07_registration.md` | Registration — التسجيل | https://reg.bethlehem.edu:100/Menu/PageDetails.aspx?catalogID=46&PageID=17&type=1 |
| `cleaned_sources/catalog_2026-2027/regulations/08_student_obligations.md` | Student Obligations — واجبات الطالب | https://reg.bethlehem.edu:100/Menu/PageDetails.aspx?catalogID=46&PageID=18&type=1 |
| `cleaned_sources/catalog_2026-2027/regulations/09_change_of_major.md` | Change of Major — تغيير التخصص | https://reg.bethlehem.edu:100/Menu/PageDetails.aspx?catalogID=46&PageID=20&type=1 |

## What was cleaned
- Removed site navigation menus, page headers and footers (contact block, "BU Online Catalogs" link).
- Kept each page's "Last Reviewed / Responsible Office / Review Cycle" line as metadata.
- Converted links to plain text; fixed escaped characters (`1\.`, `\|`) and broken formatting (`**F.****Overload:**`).
- Re-joined hard-wrapped paragraphs and table rows that were split by blank lines; turned "Credits" rows into a "Total credits this semester" line.
- Turned lettered sub-sections (A., B., …) into headings with Arabic translations, so each topic is its own search passage. Arabic titles are explanatory translations; the official text is English.
- Made every study-plan heading self-describing (program · English track · year · term).
- Fixed source typos: "PALESTININIAN" → "PALESTINIAN", "semester proceeding" → "semester preceding", "Step3" → "Step 3", "hours.." → "hours.".
- Senior Students Extra Load: list renumbered 1–5 (the source page skipped a number).
- CSSE Program of Study: the three track lists were merged (they differ only by ENGR103).
- CSSE source inconsistency (left as published): Major Requirement courses listed total 75 credits, while the CSSE Degree Requirements table says 72.

## Why the regulation pages are in `cleaned_sources/` and not in `data/`
The 9 Academic Regulations pages duplicate content already in `data/bu_academic_regulations.md`, which also covers more topics (grades, probation, withdrawal, graduation…). Indexing both would return the same passage twice and push other relevant passages out of the top results. To use the official per-page versions instead, move `bu_academic_regulations.md` out of `data/`, move the `regulations` folder into `data/catalog_2026-2027/`, and click **Rescan folder**.
