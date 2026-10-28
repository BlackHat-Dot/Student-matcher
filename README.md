# dynamic-matcher

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![Tests](https://img.shields.io/badge/tests-24%20passed-brightgreen.svg)
![Zero Dependencies](https://img.shields.io/badge/dependencies-standard%20library-orange.svg)

**dynamic-matcher** is a web application designed to compute and visualize schedule and slot compatibility between students based on their course registrations.

---

## Table of Contents
- [Overview](#overview)
- [Modes of Operation](#modes-of-operation)
- [How to Run the Application](#how-to-run-the-application)
- [Matching Algorithm](#matching-algorithm)
- [Top 5 Best Match Algorithm & Data Structures](#top-5-best-match-algorithm--data-structures)
- [Validation & Error Handling](#validation--error-handling)
- [Handling Missing Data](#handling-missing-data)
- [Testing](#testing)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)

---

## Overview

The application features two matching modes:
1. **One Student & Best 5 Show**: Select any student and instantly discover their **Top 5 most compatible peers** across the entire 1,555-student database using an Inverted Slot Index and Min-Heap Priority Queue.
2. **Compare Two Students (1 vs 1)**: Directly compare any two students head-to-head with precise match percentage and course-by-course breakdown.

Key Highlights:
- **Instant Search Suggestions**: Prefetches the 1,555 student name index on app load, delivering instant, zero-latency autocomplete as the user types without making network requests per keystroke.
- **Accurate Slot Parsing**: Extracts theory slot codes, ignores lab slots, and decodes class timings (morning vs. evening).
- **Asymmetric Base Student Assignment**: Establishes the student with fewer usable courses as the baseline to ensure a fair and consistent match score.
- **Strict Validation**: Rejects identical student comparisons (hard blocks comparing a student with themselves) and verifies student presence with targeted error messaging.
- **Missing Data Adjustments**: Transparently identifies skipped courses where slot data is missing, excluding them from both matches and the baseline fingerprint.
- **Interactive UI**: Responsive desktop and mobile interface with mode switcher buttons, rank badges, and collapsible course breakdown tables.

---

## Modes of Operation

### 1. One Student & Best 5 Show
- Single input field with autocomplete.
- Evaluates the target student against all candidates who share at least one slot.
- Renders 5 ranked cards (#1 to #5) with match percentages, compatibility tags, and an expandable course-by-course breakdown table for each matched pair.
- Includes a **"Compare 1-on-1"** button on each card to immediately switch into head-to-head mode with that peer.

### 2. Compare Two Students (1 vs 1)
- Two text boxes for Student A and Student B with instant suggestions and a quick swap button.
- Comprehensive Hero Match Score card, base student comparison panel, stats grid (Matched, Mismatched, Skipped, Compared), and filterable breakdown tabs.

---

## How to Run the Application

The project is built with **zero external dependencies**, requiring only standard Python 3.10+ (tested on Python 3.12).

### 1. Start the Server
From the project folder, run:
```bash
python3 server.py --port 8000
```
Optional arguments:
- `--port`: Port to bind the HTTP server to (default: `8000`).
- `--host`: Host address to bind to (default: `0.0.0.0`).
- `--db`: Path to custom JSON database (default searches for `bce_students_database_1.json` or `bce_students_database.json`).

### 2. Access the Web Interface
Open your web browser and navigate to:
```
http://localhost:8000/
```

---

## Matching Algorithm (Option 2: Strict Same-Professor & Same-Slot Matching)

The matching logic follows these deterministic rules:

1. **Slot & Professor Extraction**:
   Values inside parentheses in the `faculty` field are evaluated for theory slots, and the preceding faculty string identifies the professor.
   *Example*: In `"KALYAN (E2+TE2) KALYAN (L9+L10)"`, the theory slot is `E2` and professor is `KALYAN`.

2. **Lab Classes Ignored**:
   Lab sessions are excluded from timetable theory matching. Any slot code starting with `L` (e.g., `L49`, `L9+L10`, `L31+L32+L49+L50`) is ignored.

3. **First Theory Code Only**:
   For compound theory slot codes (e.g., `E2+TE2`, `A1+TA1+TAA1`), only the primary code (`E2`, `A1`) is evaluated; subsequent tutorial tags (e.g. `TE2`, `TAA1`) are ignored.

4. **Strict Same-Professor & Same-Slot Requirement (Option 2)**:
   A course is counted as **Matched** if and only if **both** the slot code AND the exact professor match. If students are in the same slot (e.g., `B2`) but have different professors, it is counted as a **Mismatch** (`Diff Prof`).

5. **Morning vs. Evening Timings**:
   The trailing digit of the slot code designates the time of the class:
   - Trailing digit `1` $\rightarrow$ **Morning Slot** (e.g., `A1`, `B1`, `C1`, `D1`, `E1`, `F1`, `G1`, `TCC1`, `TDD1`).
   - Trailing digit `2` $\rightarrow$ **Evening Slot** (e.g., `A2`, `B2`, `C2`, `D2`, `E2`, `F2`, `G2`, `TCC2`, `TDD2`).

6. **Symmetric Union Course Evaluation**:
   - Rather than comparing against only the student with fewer courses, the comparison evaluates the **full union of unique courses** taken by both students:
     $$U = \text{usable}(A) \cup \text{usable}(B)$$
   - Courses taken by only one student are marked as **Not Enrolled** and count as mismatches, deducting score symmetrically in both directions.

7. **Match Percentage Calculation**:
   $$\text{Match Percentage} = \left(\frac{\text{Number of courses with SAME slot AND SAME professor}}{\text{Total Unique Courses} - \text{Unavailable Courses}}\right) \times 100$$
   - The match percentage is strictly symmetric: $\text{match}(A, B) \equiv \text{match}(B, A)$.
   - Comparing a 15-course student with a 3-course student who shares 3 courses yields $\frac{3}{15} = 20\%$ in both directions.

8. **Precision Rules**:
   - Integers are displayed without decimals (e.g., `72%`, `100%`, `50%`, `0%`).
   - Fractional percentages are rounded to two decimal places without forcing trailing zeros (e.g., `46.15%`, `66.67%`, `12.5%`). Never outputs fixed zero padding such as `72.00%`.

---

## Top 5 Best Match Algorithm & Data Structures

Finding the top 5 matches out of 1,555 students utilizes an optimal combination of data structures:

### 1. Dual Inverted Index (`course_slot_prof_index` & `course_slot_index`)
- **Structure**:
  - `course_slot_prof_index[course_name][(slot_code, norm_prof)] -> set(student_names)`
  - `course_slot_index[course_name][slot_code] -> set(student_names)`
- **Role**: Rather than performing a brute-force $O(N)$ pairwise scan across all 1,555 students, we query candidates sharing the exact course, slot, and professor, falling back to same-slot peers if needed.
- **Complexity**: $O(C_{\text{target}})$ lookups to identify only candidates who share relevant courses.

### 2. Min-Heap Priority Queue of Capacity $K=5$ (`heapq`)
- **Structure**: A fixed-capacity min-heap tracking the top 5 matches.
- **Score Tuple**:
  $$\text{score\_key} = (\text{match\_percentage}, \text{matched\_count}, -\text{unavailable\_count}, \text{other\_fingerprint}, \text{other\_name})$$
  - Primary sort: Highest match percentage.
  - Secondary tie-breaker: Higher count of matched courses.
  - Tertiary tie-breaker: Lower count of unavailable/skipped courses.
  - Quaternary tie-breaker: Unique student name (ensures deterministic heap ordering).
- **Complexity**: For $M$ candidates, maintaining the min-heap takes $O(M \log 5)$. Total query time is **~40–60 ms**.

---

## Validation & Error Handling

To ensure data integrity and clear user feedback:
- **Same-Student Comparison Block**:
  Comparing the same student with themselves is strictly disallowed on both client and server:
  *"Cannot compare student '...' with themselves. Please select two different students to compare."*
- **Presence Verification & Specific Not-Found Errors**:
  When evaluating input names, the system specifically distinguishes which field is invalid:
  - If neither student exists: *"Neither 'A' nor 'B' could be found in the database."*
  - If Student A is missing: *"Student A 'A' could not be found in the database."*
  - If Student B is missing: *"Student B 'B' could not be found in the database."*
- **Persistent Error Prevention**:
  CSS rule `[hidden] { display: none !important; }` guarantees error banners only appear when an active error occurs and disappear when input changes.

---

## Handling Missing Data

To ensure accurate compatibility and avoid false 100% matches:

- **Unenrolled / Not Selected Courses**:
  If a course is in the base student's usable list, but the other student did **not select or enroll** in it (e.g., elected a different course), that course is **NOT skipped**. It counts as an **unmatched course** and reduces the match percentage accordingly (e.g., 12 matches out of 13 total courses yields $92.31\%$, not $100\%$).
- **Genuine Missing Faculty Data**:
  Only courses where a student is enrolled but the faculty slot data is completely missing or unresolved (e.g., `NIL`, `ACAD FACULTY(NIL)`, aptitude-only `APT`, partial faculty arrays without slot information, or pure lab-only slots) are classified as **unavailable/skipped**:
  $$\text{Adjusted Fingerprint} = \text{Base Initial Fingerprint} - \text{Unavailable Courses}$$
  $$\text{Match Percentage} = \left(\frac{\text{Matched Courses}}{\text{Adjusted Fingerprint}}\right) \times 100$$
- **Zero Usable Courses**:
  If the base student has 0 usable courses, or if all courses are skipped due to missing data, the app displays a clear notification explaining that the match percentage cannot be computed.

---

## Testing

Run the automated test suite with Python's built-in `unittest`:
```bash
python3 -m unittest discover tests
```
19 tests covering:
- Slot parsing and Kalyan prompt example (`E2`, evening, lab ignored).
- Compound theory slots and lab filtering.
- Trailing digit morning/evening determination.
- Base student selection by fingerprint.
- Missing data handling and adjusted fingerprints.
- Same student comparison rejection (`SameStudentError`).
- Specific student not found messages.
- Top 5 best matches finding, tie-breaking, and self-exclusion.

---

## API Reference

### 1. Health Check
`GET /api/health`

### 2. Prefetch Students Index
`GET /api/students`

### 3. Find Top 5 Matches
`GET /api/top5?student=<Name or RegNo>`
- **Response**:
  ```json
  {
    "target_student": {
      "name": "S2STEVE RYAN I 25BCE1001",
      "display_name": "STEVE RYAN I",
      "reg_no": "25BCE1001",
      "fingerprint": 13
    },
    "total_matches_found": 5,
    "top_matches": [
      {
        "rank": 1,
        "matched_student_name": "V2VS VAIBHAVKRISHNA 25BCE5610",
        "matched_student_display_name": "VS VAIBHAVKRISHNA",
        "matched_student_reg_no": "25BCE5610",
        "matched_student_fingerprint": 13,
        "match_percentage": 100.0,
        "formatted_percentage": "100%",
        "matched_courses_count": 3,
        "compared_courses_count": 3,
        "comparisons": [...]
      }
    ]
  }
  ```

### 4. Compare Two Students (1 vs 1)
`GET /api/match?student_a=<Name>&student_b=<Name>`

---

## Project Structure

```
dynamic-matcher/
├── .gitignore                        # Git ignore rules for database and bytecode caches
├── matcher.py                        # Core matching engine, Inverted Index & Min-Heap
├── server.py                         # Multi-threaded HTTP server & REST API
├── static/
│   ├── css/
│   │   └── style.css                 # Modern responsive styling (desktop & mobile)
│   ├── js/
│   │   └── app.js                    # Autocomplete engine, mode switcher & UI controller
│   └── index.html                    # Single-page web application interface
├── tests/
│   ├── __init__.py
│   └── test_matcher.py               # Automated test suite (24 tests)
├── unique_courses.json               # Extracted unique course reference catalogue
└── README.md                         # Project documentation
```
