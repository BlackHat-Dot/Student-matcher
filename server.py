"""
Dynamic Matcher Web Server

Multi-threaded HTTP server providing REST API and static UI delivery.
No external dependencies required (uses standard library http.server).
"""

import argparse
import json
import mimetypes
import os
import sys
import urllib.parse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from matcher import StudentDatabase, StudentNotFoundError, SameStudentError, MatchResult

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Default database search paths
DB_PATHS = [
    os.path.join(BASE_DIR, "bce_students_database.json"),
    "bce_students_database.json",
    os.path.join(BASE_DIR, "bce_students_database_1.json"),
    "bce_students_database_1.json",
]


class DynamicMatcherHandler(SimpleHTTPRequestHandler):
    """Custom HTTP request handler for Dynamic Matcher API and static files."""

    database: StudentDatabase = None
    static_dir: str = os.path.join(BASE_DIR, "static")

    def _send_json_response(self, data: dict, status_code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status_code: int = 400):
        self._send_json_response({"error": True, "message": message}, status_code=status_code)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # API Endpoints
        if path == "/api/health":
            self._send_json_response(
                {
                    "status": "healthy",
                    "students_count": len(self.database.students) if self.database else 0,
                    "version": "1.0.0",
                }
            )
            return

        if path == "/api/students":
            if not self.database:
                self._send_error_json("Database not initialized", 500)
                return
            self._send_json_response(
                {
                    "total": len(self.database.all_students_summary),
                    "students": self.database.all_students_summary,
                }
            )
            return

        if path == "/api/search":
            q = query.get("q", [""])[0]
            try:
                limit = int(query.get("limit", [10])[0])
                limit = max(1, min(limit, 100))
            except (ValueError, TypeError):
                limit = 10

            if not self.database:
                self._send_error_json("Database not initialized", 500)
                return
            results = self.database.search_students(q, limit=limit)
            self._send_json_response({"query": q, "results": results})
            return

        if path == "/api/top5":
            student_query = query.get("student", [""])[0].strip()
            if not student_query:
                self._send_error_json("Parameter 'student' is required.")
                return

            if not self.database:
                self._send_error_json("Database not initialized", 500)
                return

            try:
                target, top_matches = self.database.find_top_matches(student_query, k=5)
            except StudentNotFoundError as e:
                self._send_error_json(str(e), 404)
                return
            except Exception as e:
                self._send_error_json(f"Error finding top matches: {str(e)}", 500)
                return

            matches_payload = []
            for rank, m in enumerate(top_matches, 1):
                matched_name = m.student_b_name if m.student_a_name == target.name else m.student_a_name
                matched_rec = self.database.students.get(matched_name)
                matches_payload.append(
                    {
                        "rank": rank,
                        "matched_student_name": matched_name,
                        "matched_student_display_name": matched_rec.display_name if matched_rec else matched_name,
                        "matched_student_reg_no": matched_rec.reg_no if matched_rec else "",
                        "matched_student_fingerprint": matched_rec.fingerprint if matched_rec else 0,
                        "base_student_name": m.base_student_name,
                        "base_fingerprint": m.base_fingerprint,
                        "other_fingerprint": m.other_fingerprint,
                        "matched_courses_count": m.matched_courses_count,
                        "mismatched_courses_count": m.mismatched_courses_count,
                        "unavailable_courses_count": m.unavailable_courses_count,
                        "compared_courses_count": m.compared_courses_count,
                        "total_unique_courses_count": m.total_unique_courses_count,
                        "adjusted_fingerprint": m.adjusted_fingerprint,
                        "adjusted_total_courses": m.adjusted_total_courses,
                        "match_percentage": m.match_percentage,
                        "formatted_percentage": m.formatted_percentage,
                        "has_usable_data": m.has_usable_data,
                        "adjustment_explanation": m.adjustment_explanation,
                        "comparisons": [
                            {
                                "course_name": c.course_name,
                                "student_a_slot": c.student_a_slot,
                                "student_a_timing": c.student_a_timing,
                                "student_a_professor": c.student_a_professor,
                                "student_b_slot": c.student_b_slot,
                                "student_b_timing": c.student_b_timing,
                                "student_b_professor": c.student_b_professor,
                                "base_slot": c.base_slot,
                                "base_timing": c.base_timing,
                                "base_professor": c.base_professor,
                                "other_slot": c.other_slot,
                                "other_timing": c.other_timing,
                                "other_professor": c.other_professor,
                                "status": c.status,
                                "reason": c.reason,
                            }
                            for c in m.comparisons
                        ],
                    }
                )

            resp = {
                "target_student": {
                    "name": target.name,
                    "display_name": target.display_name,
                    "reg_no": target.reg_no,
                    "fingerprint": target.fingerprint,
                },
                "total_matches_found": len(matches_payload),
                "top_matches": matches_payload,
            }
            self._send_json_response(resp)
            return

        if path == "/api/match":
            name_a = query.get("student_a", [""])[0].strip()
            name_b = query.get("student_b", [""])[0].strip()

            if not name_a or not name_b:
                self._send_error_json("Both 'student_a' and 'student_b' parameters are required.")
                return

            if not self.database:
                self._send_error_json("Database not initialized", 500)
                return

            try:
                result = self.database.match_students(name_a, name_b)
            except SameStudentError as e:
                self._send_error_json(str(e), 400)
                return
            except StudentNotFoundError as e:
                self._send_error_json(str(e), 404)
                return
            except Exception as e:
                self._send_error_json(f"Internal matching error: {str(e)}", 500)
                return

            # Serialize MatchResult to JSON
            resp = {
                "student_a_name": result.student_a_name,
                "student_b_name": result.student_b_name,
                "student_a_fingerprint": result.student_a_fingerprint,
                "student_b_fingerprint": result.student_b_fingerprint,
                "base_student_name": result.base_student_name,
                "other_student_name": result.other_student_name,
                "base_fingerprint": result.base_fingerprint,
                "other_fingerprint": result.other_fingerprint,
                "total_unique_courses_count": result.total_unique_courses_count,
                "compared_courses_count": result.compared_courses_count,
                "matched_courses_count": result.matched_courses_count,
                "mismatched_courses_count": result.mismatched_courses_count,
                "unavailable_courses_count": result.unavailable_courses_count,
                "adjusted_fingerprint": result.adjusted_fingerprint,
                "adjusted_total_courses": result.adjusted_total_courses,
                "match_percentage": result.match_percentage,
                "formatted_percentage": result.formatted_percentage,
                "has_usable_data": result.has_usable_data,
                "adjustment_explanation": result.adjustment_explanation,
                "comparisons": [
                    {
                        "course_name": c.course_name,
                        "student_a_slot": c.student_a_slot,
                        "student_a_timing": c.student_a_timing,
                        "student_a_professor": c.student_a_professor,
                        "student_b_slot": c.student_b_slot,
                        "student_b_timing": c.student_b_timing,
                        "student_b_professor": c.student_b_professor,
                        "base_slot": c.base_slot,
                        "base_timing": c.base_timing,
                        "base_professor": c.base_professor,
                        "other_slot": c.other_slot,
                        "other_timing": c.other_timing,
                        "other_professor": c.other_professor,
                        "status": c.status,
                        "reason": c.reason,
                    }
                    for c in result.comparisons
                ],
                "other_additional_courses": [
                    {
                        "course_name": c.course_name,
                        "slot": c.slot,
                        "timing": c.timing,
                        "professor": c.professor,
                    }
                    for c in result.other_additional_courses
                ],
            }
            self._send_json_response(resp)
            return

        # Static File Serving
        self._serve_static(path)

    def _serve_static(self, req_path: str):
        if req_path in ("/", ""):
            req_path = "/index.html"

        clean_path = os.path.normpath(req_path.lstrip("/\\")).replace("\\", "/")
        if clean_path.startswith("static/"):
            clean_path = clean_path[len("static/") :]
        elif clean_path == "static":
            clean_path = "index.html"

        full_file_path = os.path.normpath(os.path.join(self.static_dir, clean_path))

        if not os.path.exists(full_file_path) or os.path.isdir(full_file_path):
            self.send_error(404, f"File not found: {req_path}")
            return

        ctype, _ = mimetypes.guess_type(full_file_path)
        if not ctype:
            ctype = "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"

        try:
            with open(full_file_path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")


def find_database_path(explicit_path: str = None) -> str:
    if explicit_path and os.path.exists(explicit_path):
        return explicit_path
    for p in DB_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Could not find student database JSON file.")


def main():
    parser = argparse.ArgumentParser(description="Run Dynamic Matcher web application.")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Server host (default: 0.0.0.0)")
    parser.add_argument("--db", type=str, default=None, help="Path to student database JSON file")
    args = parser.parse_args()

    db_path = find_database_path(args.db)
    print(f"Loading student database from: {db_path}...")
    db = StudentDatabase(db_path)
    print(f"Pre-processed {len(db.students)} students successfully.")

    DynamicMatcherHandler.database = db

    server_address = (args.host, args.port)
    httpd = ThreadingHTTPServer(server_address, DynamicMatcherHandler)
    print(f"Dynamic Matcher server running at http://localhost:{args.port}/")
    print("Press Ctrl+C to stop.")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer shutting down gracefully.")
        httpd.server_close()


if __name__ == "__main__":
    main()
