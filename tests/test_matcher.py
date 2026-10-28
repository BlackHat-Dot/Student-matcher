"""
Unit and Integration Tests for Dynamic Matcher
"""

import unittest
from matcher import (
    extract_theory_slot,
    extract_theory_slot_and_professor,
    get_slot_timing,
    format_percentage,
    StudentDatabase,
    StudentNotFoundError,
    SameStudentError,
    StudentRecord,
    CourseInfo,
)


class TestSlotExtraction(unittest.TestCase):
    """Test slot extraction and timing rules."""

    def test_prompt_example_kalyan(self):
        """
        Verify the exact example from the prompt:
        'KALYAN (E2+TE2) KALYAN (L9+L10)' -> theory slot E2, evening, lab ignored.
        """
        faculty = "KALYAN (E2+TE2) KALYAN (L9+L10)"
        slot = extract_theory_slot(faculty)
        self.assertEqual(slot, "E2")
        timing = get_slot_timing(slot)
        self.assertEqual(timing, "Evening")

    def test_compound_theory_slots(self):
        """Rule 3: From a theory value such as E2+TE2, use only first code."""
        self.assertEqual(extract_theory_slot("PROF (A1+TA1)"), "A1")
        self.assertEqual(extract_theory_slot("PROF (A1+TA1+TAA1)"), "A1")
        self.assertEqual(extract_theory_slot("PROF (B2+TB2)"), "B2")
        self.assertEqual(extract_theory_slot("PROF (C1+TC1+TCC1)"), "C1")
        self.assertEqual(extract_theory_slot("PROF (D2+TD2+TDD2)"), "D2")
        self.assertEqual(extract_theory_slot("PROF (TCC1)"), "TCC1")
        self.assertEqual(extract_theory_slot("PROF (TDD2)"), "TDD2")

    def test_pure_lab_slots_ignored(self):
        """Rule 2: Lab classes are not part of the match. Ignore any value starting with L."""
        self.assertIsNone(extract_theory_slot("PROF (L49)"))
        self.assertIsNone(extract_theory_slot("PROF (L9+L10)"))
        self.assertIsNone(extract_theory_slot("PROF (L31+L32+L49+L50)"))
        self.assertIsNone(extract_theory_slot("PRASSANNA J(L31+L32+L49+L50)"))
        self.assertIsNone(extract_theory_slot("JANAKI MEENA M(L51+L52+L55+L56)"))

    def test_non_slot_markers(self):
        """Handle NIL, ACAD FACULTY(NIL), APT, and partial lists."""
        self.assertIsNone(extract_theory_slot("MAHALAKSHMI S(NIL)"))
        self.assertIsNone(extract_theory_slot("ACAD FACULTY(NIL)"))
        self.assertIsNone(extract_theory_slot("NIL"))
        self.assertIsNone(extract_theory_slot(None))
        self.assertIsNone(extract_theory_slot(["SAVARIAH XAVIER Y C 50070", "SHALINI SUPRIYA 54182"]))

    def test_aptitude_compound_slot(self):
        """Ensure (APT) is ignored and subsequent theory slot is extracted."""
        self.assertEqual(extract_theory_slot("FACE (APT)(F2+TF2)"), "F2")
        self.assertEqual(extract_theory_slot("ETHNUS (APT)(B1+TB1)"), "B1")

    def test_slot_timing(self):
        """Rule 4: Code ending in 1 is morning, 2 is evening."""
        self.assertEqual(get_slot_timing("A1"), "Morning")
        self.assertEqual(get_slot_timing("E1"), "Morning")
        self.assertEqual(get_slot_timing("TCC1"), "Morning")
        self.assertEqual(get_slot_timing("TDD1"), "Morning")

        self.assertEqual(get_slot_timing("A2"), "Evening")
        self.assertEqual(get_slot_timing("E2"), "Evening")
        self.assertEqual(get_slot_timing("TCC2"), "Evening")
        self.assertEqual(get_slot_timing("TDD2"), "Evening")

        self.assertEqual(get_slot_timing(None), "Unavailable")
        self.assertEqual(get_slot_timing(""), "Unavailable")
        self.assertEqual(get_slot_timing("XYZ"), "Unknown")


class TestPrecisionFormatting(unittest.TestCase):
    """Test match percentage precision rules."""

    def test_integer_percentages(self):
        """No decimals for integer percentages."""
        self.assertEqual(format_percentage(100.0), "100%")
        self.assertEqual(format_percentage(72.0), "72%")
        self.assertEqual(format_percentage(0.0), "0%")
        self.assertEqual(format_percentage(50.0), "50%")

    def test_decimal_percentages(self):
        """Show decimals only when needed without forcing fixed digits."""
        self.assertEqual(format_percentage(66.666667), "66.67%")
        self.assertEqual(format_percentage(33.333333), "33.33%")
        self.assertEqual(format_percentage(12.5), "12.5%")
        self.assertEqual(format_percentage(87.5), "87.5%")
        self.assertEqual(format_percentage(7.142857), "7.14%")

    def test_none_percentage(self):
        self.assertEqual(format_percentage(None), "N/A")


class TestMatchingAlgorithm(unittest.TestCase):
    """Test matching logic, base student selection, and missing data adjustments."""

    def setUp(self):
        self.db = StudentDatabase()

    def _create_mock_student(self, name: str, course_slots: dict) -> StudentRecord:
        courses = {}
        usable = {}
        for cname, raw_fac in course_slots.items():
            slot, prof = extract_theory_slot_and_professor(raw_fac)
            timing = get_slot_timing(slot)
            is_usable = slot is not None
            courses[cname] = CourseInfo(
                course_name=cname,
                raw_faculty=raw_fac,
                status="Exact" if is_usable else "NIL",
                slot=slot,
                timing=timing,
                professor=prof,
                is_usable=is_usable,
            )
            if is_usable:
                usable[cname] = (slot, prof)

        rec = StudentRecord(
            name=name,
            profile_url="http://example.com",
            reg_no="25BCE9999",
            display_name=name,
            courses=courses,
            usable_courses=usable,
            fingerprint=len(usable),
        )
        self.db.students[name] = rec
        self.db.normalized_name_map[name.lower()] = name
        return rec

    def test_disallow_comparing_same_student(self):
        """Disallow comparing the same student with themselves."""
        self._create_mock_student(
            "Student Solo",
            {
                "Math": "PROF (A1+TA1)",
                "Physics": "PROF (B1+TB1)",
            },
        )
        with self.assertRaises(SameStudentError) as ctx:
            self.db.match_students("Student Solo", "Student Solo")
        self.assertIn("Cannot compare student", str(ctx.exception))
        self.assertIn("with themselves", str(ctx.exception))

    def test_symmetric_matching_between_students_with_unequal_courses(self):
        """Symmetric matching: Deduct score equally regardless of comparison order."""
        # Student Alpha has 2 usable courses
        self._create_mock_student(
            "Student Alpha",
            {
                "Math": "PROF (A1+TA1)",
                "Physics": "PROF (B1+TB1)",
            },
        )
        # Student Beta has 3 usable courses
        self._create_mock_student(
            "Student Beta",
            {
                "Math": "PROF (A1+TA1)",
                "Physics": "PROF (B1+TB1)",
                "Chemistry": "PROF (C1+TC1)",
            },
        )

        # Alpha vs Beta: 2 matched, 1 mismatched (Chem) out of 3 union courses = 66.67%
        res_ab = self.db.match_students("Student Alpha", "Student Beta")
        self.assertEqual(res_ab.total_unique_courses_count, 3)
        self.assertEqual(res_ab.matched_courses_count, 2)
        self.assertEqual(res_ab.mismatched_courses_count, 1)
        self.assertEqual(res_ab.formatted_percentage, "66.67%")

        # Beta vs Alpha: Exact same 66.67% (symmetric deduction)
        res_ba = self.db.match_students("Student Beta", "Student Alpha")
        self.assertEqual(res_ba.total_unique_courses_count, 3)
        self.assertEqual(res_ba.matched_courses_count, 2)
        self.assertEqual(res_ba.mismatched_courses_count, 1)
        self.assertEqual(res_ba.formatted_percentage, "66.67%")
        self.assertEqual(res_ab.match_percentage, res_ba.match_percentage)

    def test_missing_data_adjustment(self):
        """
        Missing Data:
        - Do not count unavailable courses (NIL) as match or mismatch.
        - Deduct from total union courses (adjusted total).
        """
        self._create_mock_student(
            "Student Base",
            {
                "Course 1": "PROF (E1+TE1)",
                "Course 2": "PROF (A2+TA2)",
                "Course 3": "PROF (B1+TB1)",
            },
        )
        self._create_mock_student(
            "Student Other",
            {
                "Course 1": "PROF (E1+TE1)",
                "Course 2": "PROF (A1+TA1)",
                "Course 3": "PROF (NIL)",
                "Course 4": "PROF (C2+TC2)",
            },
        )

        res = self.db.match_students("Student Base", "Student Other")
        self.assertEqual(res.total_unique_courses_count, 4)
        self.assertEqual(res.matched_courses_count, 1)  # Course 1
        self.assertEqual(res.mismatched_courses_count, 2)  # Course 2 (diff slot) + Course 4 (not enrolled by Base)
        self.assertEqual(res.unavailable_courses_count, 1)  # Course 3 (NIL for Other)
        self.assertEqual(res.compared_courses_count, 3)
        self.assertEqual(res.adjusted_total_courses, 3)
        # Match % = 1 / 3 * 100 = 33.33%
        self.assertEqual(res.formatted_percentage, "33.33%")
        self.assertIn("1 skipped due to missing database allocation", res.adjustment_explanation)

    def test_not_enrolled_course_reduces_percentage_and_not_skipped(self):
        """
        Courses enrolled by only one student count as mismatched and reduce percentage:
        Deduction is symmetric in both directions.
        """
        self._create_mock_student(
            "Student Base Enrolled",
            {
                "Math": "PROF (A1+TA1)",
                "Physics": "PROF (B1+TB1)",
            },
        )
        self._create_mock_student(
            "Student Other Not Enrolled",
            {
                "Math": "PROF (A1+TA1)",
                # Physics not enrolled!
            },
        )

        res_ab = self.db.match_students("Student Base Enrolled", "Student Other Not Enrolled")
        self.assertEqual(res_ab.total_unique_courses_count, 2)
        self.assertEqual(res_ab.matched_courses_count, 1)
        self.assertEqual(res_ab.mismatched_courses_count, 1)
        self.assertEqual(res_ab.formatted_percentage, "50%")

        res_ba = self.db.match_students("Student Other Not Enrolled", "Student Base Enrolled")
        self.assertEqual(res_ba.total_unique_courses_count, 2)
        self.assertEqual(res_ba.matched_courses_count, 1)
        self.assertEqual(res_ba.mismatched_courses_count, 1)
        self.assertEqual(res_ba.formatted_percentage, "50%")

        # Comparing 3 courses vs 3 courses where 1 course differs on each side
        self._create_mock_student(
            "Student A 3 courses",
            {
                "Course 1": "PROF (A1+TA1)",
                "Course 2": "PROF (B1+TB1)",
                "Course 3": "PROF (C1+TC1)",
            },
        )
        self._create_mock_student(
            "Student B 3 courses",
            {
                "Course 1": "PROF (A1+TA1)",
                "Course 2": "PROF (B1+TB1)",
                "Course 4": "PROF (D1+TD1)",
            },
        )
        res2 = self.db.match_students("Student A 3 courses", "Student B 3 courses")
        # Union has 4 courses (1, 2, 3, 4). 2 matched (1, 2), 2 mismatched (3, 4) -> 2 / 4 = 50%
        self.assertEqual(res2.total_unique_courses_count, 4)
        self.assertEqual(res2.matched_courses_count, 2)
        self.assertEqual(res2.mismatched_courses_count, 2)
        self.assertEqual(res2.unavailable_courses_count, 0)
        self.assertEqual(res2.formatted_percentage, "50%")

    def test_zero_usable_courses_base_student(self):
        """Missing Data: If base student has no usable courses, show clear message instead of percentage."""
        self._create_mock_student(
            "Zero Student",
            {
                "Course 1": "PROF (NIL)",
                "Course 2": "PROF (L1+L2)",
            },
        )
        self._create_mock_student(
            "Normal Student",
            {
                "Course 1": "PROF (A1+TA1)",
            },
        )

        res = self.db.match_students("Zero Student", "Normal Student")
        self.assertFalse(res.has_usable_data)
        self.assertIsNone(res.match_percentage)
        self.assertEqual(res.formatted_percentage, "N/A")
        self.assertIn("skipped because data was unavailable", res.adjustment_explanation)

        # When neither student has any usable courses
        self._create_mock_student(
            "Zero Student 2",
            {
                "Course X": "PROF (NIL)",
            },
        )
        res_both_zero = self.db.match_students("Zero Student", "Zero Student 2")
        self.assertFalse(res_both_zero.has_usable_data)
        self.assertIsNone(res_both_zero.match_percentage)
        self.assertEqual(res_both_zero.formatted_percentage, "N/A")
        self.assertIn("Neither student has usable courses", res_both_zero.adjustment_explanation)

    def test_specific_student_not_found_errors(self):
        """Hard block and verify specific not-found error messages."""
        self._create_mock_student(
            "Existing Student",
            {"Math": "PROF (A1+TA1)"},
        )

        # Neither found
        with self.assertRaises(StudentNotFoundError) as ctx1:
            self.db.match_students("Ghost A", "Ghost B")
        self.assertIn("Neither 'Ghost A' nor 'Ghost B' could be found", str(ctx1.exception))

        # Student A not found
        with self.assertRaises(StudentNotFoundError) as ctx2:
            self.db.match_students("Ghost A", "Existing Student")
        self.assertIn("Student A 'Ghost A' could not be found", str(ctx2.exception))

        # Student B not found
        with self.assertRaises(StudentNotFoundError) as ctx3:
            self.db.match_students("Existing Student", "Ghost B")
        self.assertIn("Student B 'Ghost B' could not be found", str(ctx3.exception))

    def test_option2_strict_professor_matching(self):
        """
        Option 2: Strict Same-Professor and Same-Slot Matching.
        - Same slot AND same professor -> Matched.
        - Same slot BUT different professor -> Mismatched.
        - Different slot -> Mismatched.
        """
        self._create_mock_student(
            "Student Prof A",
            {
                "Math": "PROF ALICE (A1+TA1)",
                "Physics": "PROF BOB (B1+TB1)",
                "Chemistry": "PROF CHARLIE (C1+TC1)",
            },
        )
        self._create_mock_student(
            "Student Prof B",
            {
                "Math": "PROF ALICE (A1+TA1)",       # Same slot, same prof -> MATCH
                "Physics": "PROF DAVE (B1+TB1)",       # Same slot, different prof -> MISMATCH
                "Chemistry": "PROF CHARLIE (C2+TC2)", # Different slot -> MISMATCH
            },
        )

        res = self.db.match_students("Student Prof A", "Student Prof B")
        self.assertEqual(res.base_fingerprint, 3)
        self.assertEqual(res.matched_courses_count, 1)  # Math only
        self.assertEqual(res.mismatched_courses_count, 2)  # Physics (diff prof) and Chem (diff slot)
        self.assertEqual(res.formatted_percentage, "33.33%")

        # Verify comparison details
        math_comp = next(c for c in res.comparisons if c.course_name == "Math")
        self.assertEqual(math_comp.status, "matched")
        self.assertEqual(math_comp.base_professor, "PROF ALICE")
        self.assertEqual(math_comp.other_professor, "PROF ALICE")

        physics_comp = next(c for c in res.comparisons if c.course_name == "Physics")
        self.assertEqual(physics_comp.status, "mismatched")
        self.assertEqual(physics_comp.base_professor, "PROF BOB")
        self.assertEqual(physics_comp.other_professor, "PROF DAVE")
        self.assertIn("different professors", physics_comp.reason)


class TestDatabaseIntegration(unittest.TestCase):
    """Integration test loading the real dataset."""

    @classmethod
    def setUpClass(cls):
        cls.db = StudentDatabase("bce_students_database.json")

    def test_database_loaded_successfully(self):
        self.assertEqual(len(self.db.students), 1555)
        self.assertEqual(len(self.db.all_students_summary), 1555)

    def test_search_prefix(self):
        results = self.db.search_students("steve", limit=5)
        self.assertGreater(len(results), 0)
        self.assertTrue(any("STEVE" in r["name"] for r in results))

    def test_disallow_self_match_on_real_db(self):
        first_student = list(self.db.students.keys())[0]
        with self.assertRaises(SameStudentError):
            self.db.match_students(first_student, first_student)

    def test_distinct_students_match(self):
        names = list(self.db.students.keys())[:2]
        res = self.db.match_students(names[0], names[1])
        self.assertIsNotNone(res.match_percentage)
        self.assertIn("%", res.formatted_percentage)

    def test_find_top_5_matches(self):
        first_student = list(self.db.students.keys())[0]
        target, top_matches = self.db.find_top_matches(first_student, k=5)
        self.assertEqual(len(top_matches), 5)
        self.assertEqual(target.name, first_student)
        # Verify self is not in top matches
        for m in top_matches:
            other = m.student_b_name if m.student_a_name == target.name else m.student_a_name
            self.assertNotEqual(other, target.name)
            self.assertIsNotNone(m.match_percentage)
        # Verify sorted descending
        for i in range(len(top_matches) - 1):
            self.assertGreaterEqual(top_matches[i].match_percentage, top_matches[i + 1].match_percentage)

    def test_user_screenshot_arsh_vs_riyan(self):
        """
        Verify the exact scenario from user's screenshot under Option 2:
        A2ARSH 25BCE1116 vs S2SYED KHUNDMIR RIYAN 25BCE1988
        Both have 13 usable courses. 12 courses share same slot times.
        Under Option 2 + Symmetric Union Matching:
        - 14 unique courses across both students.
        - 6 courses share slot AND professor -> MATCH
        - 6 courses share slot BUT different professor -> MISMATCH
        - 1 course (Discrete Math) enrolled only by Arsh -> MISMATCH
        - 1 course (Augmented Reality) enrolled only by Riyan -> MISMATCH
        Total: 6 matched / 14 courses = 42.86% in both directions.
        """
        res_ab = self.db.match_students("A2ARSH 25BCE1116", "S2SYED KHUNDMIR RIYAN 25BCE1988")
        self.assertEqual(res_ab.total_unique_courses_count, 14)
        self.assertEqual(res_ab.matched_courses_count, 6)
        self.assertEqual(res_ab.mismatched_courses_count, 8)
        self.assertEqual(res_ab.unavailable_courses_count, 0)
        self.assertEqual(res_ab.compared_courses_count, 14)
        self.assertEqual(res_ab.formatted_percentage, "42.86%")

        res_ba = self.db.match_students("S2SYED KHUNDMIR RIYAN 25BCE1988", "A2ARSH 25BCE1116")
        self.assertEqual(res_ba.total_unique_courses_count, 14)
        self.assertEqual(res_ba.matched_courses_count, 6)
        self.assertEqual(res_ba.mismatched_courses_count, 8)
        self.assertEqual(res_ba.formatted_percentage, "42.86%")
        self.assertEqual(res_ab.match_percentage, res_ba.match_percentage)

    def test_sakthi_sundar_vs_narendran_symmetric_20_percent(self):
        """
        Verify Sakthi Sundar (15 courses) vs Narendran (3 courses):
        - Total unique courses: 15.
        - 3 courses match on slot and professor.
        - 12 courses enrolled only by Sakthi Sundar.
        - Match percentage = 3 / 15 * 100 = 20% in both directions!
        """
        res_sn = self.db.match_students("S2SAKTHI SUNDAR. M 25BCE1244", "N2NARENDRAN B 25BCE1061")
        self.assertEqual(res_sn.total_unique_courses_count, 15)
        self.assertEqual(res_sn.matched_courses_count, 3)
        self.assertEqual(res_sn.mismatched_courses_count, 12)
        self.assertEqual(res_sn.formatted_percentage, "20%")

        res_ns = self.db.match_students("N2NARENDRAN B 25BCE1061", "S2SAKTHI SUNDAR. M 25BCE1244")
        self.assertEqual(res_ns.total_unique_courses_count, 15)
        self.assertEqual(res_ns.matched_courses_count, 3)
        self.assertEqual(res_ns.mismatched_courses_count, 12)
        self.assertEqual(res_ns.formatted_percentage, "20%")
        self.assertEqual(res_sn.match_percentage, res_ns.match_percentage)

    def test_get_student_by_display_name(self):
        """Verify student can be looked up by unique display name despite substring collisions."""
        student = self.db.get_student("ADITYA")
        self.assertEqual(student.name, "S2S ADITYA 25BCE1025")
        self.assertEqual(student.display_name, "ADITYA")
        self.assertEqual(student.reg_no, "25BCE1025")


if __name__ == "__main__":
    unittest.main()
