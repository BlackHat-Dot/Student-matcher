"""
Dynamic Matcher Core Module

Option 2: Strict Same-Professor and Same-Slot Matching.
Requires BOTH the same slot AND the same professor for a course to count as a match.
Handles parsing of student database, slot code and professor extraction, timing calculation,
in-memory indexing, and student matching algorithm according to project rules.
"""

import heapq
import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


def normalize_professor(raw_name: Optional[str]) -> str:
    """Normalize professor name for comparison: strip punctuation dots, excess whitespace, uppercase."""
    if not raw_name:
        return ""
    # Replace dots and multiple spaces with a single space
    cleaned = re.sub(r"[\.\s]+", " ", raw_name).strip().upper()
    return cleaned


def extract_theory_slot_and_professor(faculty: any) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract the primary theory slot code AND professor name from a faculty field.
    Rules:
    1. Parentheses contain slots. In 'KALYAN (E2+TE2) KALYAN (L9+L10)', theory slot is E2 and professor is KALYAN.
    2. Lab classes (starting with 'L', e.g. L49, L9+L10) are ignored.
    3. From a theory value such as E2+TE2, use only the first code (E2).
    4. Ignore non-slot markers like NIL, ACAD FACULTY(NIL), APT, and partial lists.
    """
    if not isinstance(faculty, str):
        return None, None

    # Matches pattern: non-parentheses prefix followed by (content)
    matches = re.findall(r"([^(]*)\(([^)]+)\)", faculty)
    for prefix, content in matches:
        content_clean = content.strip()
        if not content_clean or content_clean.upper() in ("NIL", "APT") or content_clean.upper().startswith("L"):
            continue

        parts = [p.strip() for p in content_clean.split("+") if p.strip()]
        if not parts:
            continue

        first_code = parts[0]
        if first_code.upper().startswith("L") or first_code.upper() in ("NIL", "APT"):
            continue

        # Found the theory slot!
        prof = prefix.strip()
        # Handle cases like 'FACE (APT)(F2+TF2)' where prefix of (F2+TF2) is empty
        if not prof:
            idx = faculty.find("(" + content + ")")
            before = faculty[:idx].strip()
            # Remove previous parentheses e.g. (APT)
            before = re.sub(r"\([^)]*\)", "", before).strip()
            prof = before

        # Clean up any trailing/leading symbols
        prof = re.sub(r"[\.\s]+", " ", prof).strip()
        return first_code, prof if prof else None

    return None, None


def extract_theory_slot(faculty: any) -> Optional[str]:
    """Backward-compatible helper returning just the theory slot."""
    slot, _ = extract_theory_slot_and_professor(faculty)
    return slot


def get_slot_timing(slot_code: Optional[str]) -> str:
    """
    Determine the time of day from the trailing digit of the slot code:
    - Code ending in 1 -> 'Morning'
    - Code ending in 2 -> 'Evening'
    - None or other -> 'Unavailable' or 'Unknown'
    """
    if not slot_code:
        return "Unavailable"
    slot_code = slot_code.strip()
    if slot_code.endswith("1"):
        return "Morning"
    elif slot_code.endswith("2"):
        return "Evening"
    return "Unknown"


def format_percentage(val: Optional[float]) -> str:
    """
    Format match percentage precisely:
    - Decimals shown only when needed (e.g. 72% or 66.67%).
    - Never forces a fixed number of decimal places (e.g. not 72.00%).
    """
    if val is None:
        return "N/A"
    rounded = round(val, 2)
    if rounded == int(rounded):
        return f"{int(rounded)}%"
    formatted = f"{rounded:.2f}".rstrip("0").rstrip(".")
    return f"{formatted}%"


@dataclass
class CourseInfo:
    course_name: str
    raw_faculty: any
    status: str
    slot: Optional[str]
    timing: str
    professor: Optional[str]
    is_usable: bool


@dataclass
class StudentRecord:
    name: str
    profile_url: str
    reg_no: str
    display_name: str
    courses: Dict[str, CourseInfo]  # course_name -> CourseInfo
    usable_courses: Dict[str, Tuple[str, Optional[str]]]  # course_name -> (slot, professor)
    fingerprint: int  # count of courses with usable theory slot


@dataclass
class CourseComparison:
    course_name: str
    student_a_slot: Optional[str]
    student_a_timing: str
    student_a_professor: Optional[str]
    student_b_slot: Optional[str]
    student_b_timing: str
    student_b_professor: Optional[str]
    status: str  # 'matched', 'mismatched', 'unavailable'
    reason: str

    # Backward-compatible property aliases
    @property
    def base_slot(self) -> Optional[str]:
        return self.student_a_slot

    @property
    def base_timing(self) -> str:
        return self.student_a_timing

    @property
    def base_professor(self) -> Optional[str]:
        return self.student_a_professor

    @property
    def other_slot(self) -> Optional[str]:
        return self.student_b_slot

    @property
    def other_timing(self) -> str:
        return self.student_b_timing

    @property
    def other_professor(self) -> Optional[str]:
        return self.student_b_professor


@dataclass
class MatchResult:
    student_a_name: str
    student_b_name: str
    student_a_fingerprint: int
    student_b_fingerprint: int
    total_unique_courses_count: int
    compared_courses_count: int
    matched_courses_count: int
    mismatched_courses_count: int
    unavailable_courses_count: int
    adjusted_total_courses: int
    match_percentage: Optional[float]
    formatted_percentage: str
    has_usable_data: bool
    adjustment_explanation: str
    comparisons: List[CourseComparison]
    other_additional_courses: List[CourseInfo] = field(default_factory=list)

    # Backward-compatible property aliases
    @property
    def base_student_name(self) -> str:
        return self.student_a_name

    @property
    def other_student_name(self) -> str:
        return self.student_b_name

    @property
    def base_fingerprint(self) -> int:
        return self.student_a_fingerprint

    @property
    def other_fingerprint(self) -> int:
        return self.student_b_fingerprint

    @property
    def adjusted_fingerprint(self) -> int:
        return self.adjusted_total_courses


class StudentNotFoundError(Exception):
    pass


class SameStudentError(Exception):
    pass


class StudentDatabase:
    """
    In-memory pre-processed database of student records.
    Pre-processes JSON once on initialization into compact indexed structures.
    Supports strict same-professor & same-slot matching.
    """

    def __init__(self, json_path: Optional[str] = None):
        self.students: Dict[str, StudentRecord] = {}
        self.normalized_name_map: Dict[str, str] = {}
        self.course_slot_index: Dict[str, Dict[str, Set[str]]] = {}
        self.course_slot_prof_index: Dict[str, Dict[Tuple[str, str], Set[str]]] = {}
        self.prefix_index: Dict[str, Set[str]] = {}
        self.all_students_summary: List[Dict] = []

        if json_path:
            self.load_from_file(json_path)

    def load_from_file(self, json_path: str):
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"Database file not found: {json_path}")

        with open(json_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        self._process_records(raw_data)

    def _extract_reg_no(self, name: str) -> str:
        """Extract registration number like 25BCE1001 if present in name."""
        match = re.search(r"\b([0-9]{2}[A-Z]{3}[0-9]{4})\b", name)
        return match.group(1) if match else ""

    def _clean_display_name(self, name: str) -> str:
        """Strip leading section codes (e.g. S2, A2A) and trailing reg no for clean display."""
        s = name.strip()
        reg = self._extract_reg_no(s)
        if reg:
            s = s.replace(reg, "").strip()
        s = re.sub(r"^[A-Z0-9]{1,3}\b\s*", "", s)
        s = re.sub(r"^[A-Z][0-9]", "", s).strip()
        return s if s else name

    def _process_records(self, raw_data: List[dict]):
        self.students.clear()
        self.normalized_name_map.clear()
        self.course_slot_index.clear()
        self.course_slot_prof_index.clear()
        self.prefix_index.clear()
        self.all_students_summary.clear()

        for item in raw_data:
            full_name = item.get("Name", "").strip()
            if not full_name:
                continue

            profile_url = item.get("Profile_URL", "")
            raw_courses = item.get("Courses", [])

            courses_dict: Dict[str, CourseInfo] = {}
            usable_courses: Dict[str, Tuple[str, Optional[str]]] = {}

            for c in raw_courses:
                course_name = c.get("course_name", "").strip()
                if not course_name:
                    continue
                raw_faculty = c.get("faculty")
                status = c.get("status", "")

                slot, professor = extract_theory_slot_and_professor(raw_faculty)
                timing = get_slot_timing(slot)
                is_usable = slot is not None

                info = CourseInfo(
                    course_name=course_name,
                    raw_faculty=raw_faculty,
                    status=status,
                    slot=slot,
                    timing=timing,
                    professor=professor,
                    is_usable=is_usable,
                )
                courses_dict[course_name] = info

                if is_usable:
                    usable_courses[course_name] = (slot, professor)

                    # Reverse index: course -> slot -> students
                    if course_name not in self.course_slot_index:
                        self.course_slot_index[course_name] = {}
                    if slot not in self.course_slot_index[course_name]:
                        self.course_slot_index[course_name][slot] = set()
                    self.course_slot_index[course_name][slot].add(full_name)

                    # Reverse index: course -> (slot, norm_prof) -> students
                    norm_prof = normalize_professor(professor)
                    if course_name not in self.course_slot_prof_index:
                        self.course_slot_prof_index[course_name] = {}
                    prof_key = (slot, norm_prof)
                    if prof_key not in self.course_slot_prof_index[course_name]:
                        self.course_slot_prof_index[course_name][prof_key] = set()
                    self.course_slot_prof_index[course_name][prof_key].add(full_name)

            fingerprint = len(usable_courses)
            reg_no = self._extract_reg_no(full_name)
            display_name = self._clean_display_name(full_name)

            record = StudentRecord(
                name=full_name,
                profile_url=profile_url,
                reg_no=reg_no,
                display_name=display_name,
                courses=courses_dict,
                usable_courses=usable_courses,
                fingerprint=fingerprint,
            )

            self.students[full_name] = record
            self.normalized_name_map[full_name.lower()] = full_name
            self._index_prefixes(full_name, display_name, reg_no)

            self.all_students_summary.append(
                {
                    "name": full_name,
                    "display_name": display_name,
                    "reg_no": reg_no,
                    "fingerprint": fingerprint,
                }
            )

    def _index_prefixes(self, full_name: str, display_name: str, reg_no: str):
        """Index prefixes of all words and tokens for instantaneous suggestion lookups."""
        tokens = set()
        for word in re.findall(r"[A-Za-z0-9]+", full_name.lower()):
            tokens.add(word)
        for word in re.findall(r"[A-Za-z0-9]+", display_name.lower()):
            tokens.add(word)
        if reg_no:
            tokens.add(reg_no.lower())

        for token in tokens:
            for i in range(1, len(token) + 1):
                prefix = token[:i]
                if prefix not in self.prefix_index:
                    self.prefix_index[prefix] = set()
                self.prefix_index[prefix].add(full_name)

    def search_students(self, query: str, limit: int = 10) -> List[Dict]:
        """Fast autocomplete search using prefix index and substring ranking."""
        q = query.strip().lower()
        if not q:
            return []

        candidates = set(self.prefix_index.get(q, set()))

        if len(candidates) < limit:
            for full_name in self.students.keys():
                if q in full_name.lower():
                    candidates.add(full_name)
                if len(candidates) >= limit * 3:
                    break

        def rank_key(name: str):
            lower = name.lower()
            rec = self.students[name]
            clean_lower = rec.display_name.lower()
            reg_lower = rec.reg_no.lower()

            if lower.startswith(q) or clean_lower.startswith(q) or reg_lower.startswith(q):
                return (0, len(name), name)
            words = lower.split()
            if any(w.startswith(q) for w in words):
                return (1, len(name), name)
            return (2, len(name), name)

        sorted_candidates = sorted(candidates, key=rank_key)
        results = []
        for name in sorted_candidates[:limit]:
            rec = self.students[name]
            results.append(
                {
                    "name": rec.name,
                    "display_name": rec.display_name,
                    "reg_no": rec.reg_no,
                    "fingerprint": rec.fingerprint,
                }
            )
        return results

    def get_student(self, name_query: str) -> StudentRecord:
        """Find student by exact name, normalized name, or registration number."""
        q = name_query.strip()
        if not q:
            raise StudentNotFoundError("Student name cannot be empty.")

        if q in self.students:
            return self.students[q]

        q_lower = q.lower()
        if q_lower in self.normalized_name_map:
            return self.students[self.normalized_name_map[q_lower]]

        for rec in self.students.values():
            if rec.reg_no and rec.reg_no.lower() == q_lower:
                return rec

        matches = [name for name in self.students if q_lower in name.lower()]
        if len(matches) == 1:
            return self.students[matches[0]]

        raise StudentNotFoundError(f"Student '{name_query}' could not be found.")

    def match_students(self, name_a: str, name_b: str) -> MatchResult:
        """
        Compare two students based on project matching rules with Option 2 (Strict Same Professor):
        - Disallow comparing two identical students.
        - Student with smaller fingerprint is the base student (Student A if equal).
        - Course matches ONLY IF both students have the SAME slot AND the SAME professor.
        - Same slot but different professor counts as mismatched.
        - Not enrolled courses count as mismatched and reduce percentage.
        - Unavailable courses (missing slot in database) are excluded from fingerprint.
        - Match percentage = (matched / adjusted_fingerprint) * 100.
        """
        student_a = None
        student_b = None

        try:
            student_a = self.get_student(name_a)
        except StudentNotFoundError:
            pass

        try:
            student_b = self.get_student(name_b)
        except StudentNotFoundError:
            pass

        if not student_a and not student_b:
            raise StudentNotFoundError(f"Neither '{name_a}' nor '{name_b}' could be found in the database.")
        if not student_a:
            raise StudentNotFoundError(f"Student A '{name_a}' could not be found in the database.")
        if not student_b:
            raise StudentNotFoundError(f"Student B '{name_b}' could not be found in the database.")

        if student_a.name == student_b.name:
            raise SameStudentError(
                f"Cannot compare student '{student_a.name}' with themselves. "
                "Please select two different students to compare."
            )

        # Collect union of usable courses
        all_course_names = sorted(set(student_a.usable_courses.keys()) | set(student_b.usable_courses.keys()))
        total_unique = len(all_course_names)

        if total_unique == 0:
            return MatchResult(
                student_a_name=student_a.name,
                student_b_name=student_b.name,
                student_a_fingerprint=student_a.fingerprint,
                student_b_fingerprint=student_b.fingerprint,
                total_unique_courses_count=0,
                compared_courses_count=0,
                matched_courses_count=0,
                mismatched_courses_count=0,
                unavailable_courses_count=0,
                adjusted_total_courses=0,
                match_percentage=None,
                formatted_percentage="N/A",
                has_usable_data=False,
                adjustment_explanation="Neither student has usable courses with valid theory slots.",
                comparisons=[],
                other_additional_courses=[],
            )

        comparisons: List[CourseComparison] = []
        matched_count = 0
        mismatched_count = 0
        unavailable_count = 0

        for cname in all_course_names:
            in_a_usable = cname in student_a.usable_courses
            in_b_usable = cname in student_b.usable_courses

            if in_a_usable and in_b_usable:
                a_slot, a_prof = student_a.usable_courses[cname]
                b_slot, b_prof = student_b.usable_courses[cname]
                a_timing = get_slot_timing(a_slot)
                b_timing = get_slot_timing(b_slot)

                same_slot = (a_slot == b_slot)
                same_prof = (normalize_professor(a_prof) == normalize_professor(b_prof))

                if same_slot and same_prof:
                    matched_count += 1
                    comparisons.append(
                        CourseComparison(
                            course_name=cname,
                            student_a_slot=a_slot,
                            student_a_timing=a_timing,
                            student_a_professor=a_prof,
                            student_b_slot=b_slot,
                            student_b_timing=b_timing,
                            student_b_professor=b_prof,
                            status="matched",
                            reason=f"Exact match on slot {a_slot} ({a_timing}) and Prof. {a_prof}.",
                        )
                    )
                elif same_slot and not same_prof:
                    mismatched_count += 1
                    comparisons.append(
                        CourseComparison(
                            course_name=cname,
                            student_a_slot=a_slot,
                            student_a_timing=a_timing,
                            student_a_professor=a_prof,
                            student_b_slot=b_slot,
                            student_b_timing=b_timing,
                            student_b_professor=b_prof,
                            status="mismatched",
                            reason=(
                                f"Same slot {a_slot} ({a_timing}), but different professors: "
                                f"{student_a.display_name} has Prof. {a_prof} vs {student_b.display_name} has Prof. {b_prof}."
                            ),
                        )
                    )
                else:
                    mismatched_count += 1
                    comparisons.append(
                        CourseComparison(
                            course_name=cname,
                            student_a_slot=a_slot,
                            student_a_timing=a_timing,
                            student_a_professor=a_prof,
                            student_b_slot=b_slot,
                            student_b_timing=b_timing,
                            student_b_professor=b_prof,
                            status="mismatched",
                            reason=(
                                f"Slot mismatch: {student_a.display_name} has {a_slot} ({a_timing}, Prof. {a_prof}) vs "
                                f"{student_b.display_name} has {b_slot} ({b_timing}, Prof. {b_prof})."
                            ),
                        )
                    )

            elif in_a_usable and not in_b_usable:
                a_slot, a_prof = student_a.usable_courses[cname]
                a_timing = get_slot_timing(a_slot)

                if cname in student_b.courses and not student_b.courses[cname].is_usable:
                    unavailable_count += 1
                    comparisons.append(
                        CourseComparison(
                            course_name=cname,
                            student_a_slot=a_slot,
                            student_a_timing=a_timing,
                            student_a_professor=a_prof,
                            student_b_slot=None,
                            student_b_timing="Unavailable",
                            student_b_professor=None,
                            status="unavailable",
                            reason=f"Faculty slot unavailable for {student_b.display_name} (NIL or partial list). Skipped from total.",
                        )
                    )
                else:
                    mismatched_count += 1
                    comparisons.append(
                        CourseComparison(
                            course_name=cname,
                            student_a_slot=a_slot,
                            student_a_timing=a_timing,
                            student_a_professor=a_prof,
                            student_b_slot=None,
                            student_b_timing="Not Enrolled",
                            student_b_professor=None,
                            status="mismatched",
                            reason=f"Course enrolled only by {student_a.display_name} (not enrolled by {student_b.display_name}). Counts as mismatch.",
                        )
                    )

            elif not in_a_usable and in_b_usable:
                b_slot, b_prof = student_b.usable_courses[cname]
                b_timing = get_slot_timing(b_slot)

                if cname in student_a.courses and not student_a.courses[cname].is_usable:
                    unavailable_count += 1
                    comparisons.append(
                        CourseComparison(
                            course_name=cname,
                            student_a_slot=None,
                            student_a_timing="Unavailable",
                            student_a_professor=None,
                            student_b_slot=b_slot,
                            student_b_timing=b_timing,
                            student_b_professor=b_prof,
                            status="unavailable",
                            reason=f"Faculty slot unavailable for {student_a.display_name} (NIL or partial list). Skipped from total.",
                        )
                    )
                else:
                    mismatched_count += 1
                    comparisons.append(
                        CourseComparison(
                            course_name=cname,
                            student_a_slot=None,
                            student_a_timing="Not Enrolled",
                            student_a_professor=None,
                            student_b_slot=b_slot,
                            student_b_timing=b_timing,
                            student_b_professor=b_prof,
                            status="mismatched",
                            reason=f"Course enrolled only by {student_b.display_name} (not enrolled by {student_a.display_name}). Counts as mismatch.",
                        )
                    )

        compared_count = matched_count + mismatched_count
        adjusted_total = total_unique - unavailable_count

        if adjusted_total <= 0:
            match_pct = None
            formatted_pct = "N/A"
            has_data = False
            explanation = (
                f"All {total_unique} courses across both students were skipped because data "
                "was unavailable. Match percentage cannot be calculated."
            )
        else:
            has_data = True
            match_pct = (matched_count / adjusted_total) * 100.0
            formatted_pct = format_percentage(match_pct)
            if unavailable_count > 0:
                explanation = (
                    f"Evaluated all {total_unique} unique courses across both students: "
                    f"{matched_count} matched, {mismatched_count} different, and {unavailable_count} "
                    f"skipped due to missing database allocation. Total compared: {compared_count}."
                )
            else:
                explanation = (
                    f"Evaluated all {total_unique} unique courses across both students: "
                    f"{matched_count} matched, {mismatched_count} different. Total compared: {compared_count}."
                )

        return MatchResult(
            student_a_name=student_a.name,
            student_b_name=student_b.name,
            student_a_fingerprint=student_a.fingerprint,
            student_b_fingerprint=student_b.fingerprint,
            total_unique_courses_count=total_unique,
            compared_courses_count=compared_count,
            matched_courses_count=matched_count,
            mismatched_courses_count=mismatched_count,
            unavailable_courses_count=unavailable_count,
            adjusted_total_courses=adjusted_total,
            match_percentage=match_pct,
            formatted_percentage=formatted_pct,
            has_usable_data=has_data,
            adjustment_explanation=explanation,
            comparisons=comparisons,
            other_additional_courses=[],
        )

    def find_top_matches(self, student_query: str, k: int = 5) -> Tuple[StudentRecord, List[MatchResult]]:
        """
        Find top K best matches for a student under Option 2 (Strict Same Professor + Same Slot).
        Uses inverted index of (slot, norm_prof) pairs to quickly filter candidates sharing courses.
        """
        target = self.get_student(student_query)

        if target.fingerprint == 0:
            return target, []

        candidate_shared_counts = {}
        for cname, (slot, prof) in target.usable_courses.items():
            norm_prof = normalize_professor(prof)
            # Check students sharing both course, slot, and professor
            prof_students = self.course_slot_prof_index.get(cname, {}).get((slot, norm_prof), set())
            for other_name in prof_students:
                if other_name != target.name:
                    candidate_shared_counts[other_name] = candidate_shared_counts.get(other_name, 0) + 1

        # If few candidates share exact professor, fallback to candidates sharing slot
        if len(candidate_shared_counts) < k:
            for cname, (slot, _) in target.usable_courses.items():
                slot_students = self.course_slot_index.get(cname, {}).get(slot, set())
                for other_name in slot_students:
                    if other_name != target.name and other_name not in candidate_shared_counts:
                        candidate_shared_counts[other_name] = 0

        candidate_names = (
            list(candidate_shared_counts.keys())
            if candidate_shared_counts
            else [n for n in self.students if n != target.name]
        )

        heap = []
        for other_name in candidate_names:
            try:
                res = self.match_students(target.name, other_name)
            except SameStudentError:
                continue
            except StudentNotFoundError:
                continue

            if not res.has_usable_data or res.match_percentage is None:
                continue

            # Rank key: (match_pct, matched_count, -unavail_count, other_fingerprint, other_name)
            score_key = (
                res.match_percentage,
                res.matched_courses_count,
                -res.unavailable_courses_count,
                res.other_fingerprint,
                other_name,
            )

            if len(heap) < k:
                heapq.heappush(heap, (score_key, res))
            else:
                if score_key > heap[0][0]:
                    heapq.heapreplace(heap, (score_key, res))

        sorted_matches = [res for _, res in sorted(heap, key=lambda x: x[0], reverse=True)]
        return target, sorted_matches
