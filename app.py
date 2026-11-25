import os
import re
import sqlite3
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request,
    redirect, url_for, jsonify, g, session
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "mevi-workshop-development-key"
)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Database configuration
os.makedirs(app.instance_path, exist_ok=True)

DATABASE = os.environ.get(
    "DATABASE_PATH",
    os.path.join(app.instance_path, "management.db")
)

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Configurable grading rules (percentage threshold -> letter grade)
GRADING_SCALE = [
    {"min_percentage": 90.0, "grade": "A+"},
    {"min_percentage": 80.0, "grade": "A"},
    {"min_percentage": 70.0, "grade": "B+"},
    {"min_percentage": 60.0, "grade": "B"},
    {"min_percentage": 50.0, "grade": "C"},
    {"min_percentage": 40.0, "grade": "D"},
    {"min_percentage": 0.0, "grade": "F"},
]


def compute_grade(percentage, marks_obtained, pass_marks):
    if marks_obtained < pass_marks:
        return "F", "Fail"
    for rule in GRADING_SCALE:
        if percentage >= rule["min_percentage"]:
            return rule["grade"], "Pass"
    return "F", "Fail"


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE, timeout=10)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def table_columns(db, table_name):
    return [r[1] for r in db.execute(f"PRAGMA table_info({table_name})").fetchall()]


def table_exists(db, table_name):
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    ).fetchone()
    return row is not None


def init_db():
    with sqlite3.connect(DATABASE, timeout=10) as db:
        db.execute("PRAGMA foreign_keys = OFF")

        # 1. Departments
        db.execute("""
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                code TEXT NOT NULL UNIQUE,
                manager_name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Seed default departments if empty
        if db.execute("SELECT COUNT(*) FROM departments").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO departments (name, code, manager_name, description) VALUES (?, ?, ?, ?)",
                [
                    ("Computer Science", "CS", "Dr. Aarav Sharma", "Software systems, algorithms, and AI"),
                    ("Data Science", "DS", "Dr. Priya Nair", "Machine learning, statistics, and analytics"),
                    ("Business Administration", "BBA", "Prof. Rohan Mehta", "Management, finance, and operations"),
                ]
            )

        # 2. Courses
        db.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_code TEXT NOT NULL UNIQUE,
                course_name TEXT NOT NULL,
                department_id INTEGER NOT NULL,
                duration TEXT NOT NULL DEFAULT '4 Years',
                num_semesters INTEGER NOT NULL DEFAULT 8,
                description TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE RESTRICT
            )
        """)

        if db.execute("SELECT COUNT(*) FROM courses").fetchone()[0] == 0:
            cs_id = db.execute("SELECT id FROM departments ORDER BY id ASC LIMIT 1").fetchone()[0]
            ds_row = db.execute("SELECT id FROM departments WHERE code = 'DS'").fetchone()
            ds_id = ds_row[0] if ds_row else cs_id
            db.executemany(
                """
                INSERT INTO courses (course_code, course_name, department_id, duration, num_semesters, description)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    ("CS101", "B.Tech Computer Science", cs_id, "4 Years", 8, "Core computer science and software engineering"),
                    ("DS201", "B.Sc Data Science", ds_id, "3 Years", 6, "Applied statistics, data engineering, and ML"),
                ]
            )

        # 3. Migrate legacy students table if it lacks student_code
        legacy_students_rows = []
        if table_exists(db, "students") and "student_code" not in table_columns(db, "students"):
            legacy_students_rows = db.execute("SELECT id, name, email, course FROM students").fetchall()
            if not table_exists(db, "students_legacy"):
                db.execute("ALTER TABLE students RENAME TO students_legacy")
            else:
                db.execute("DROP TABLE students")

        db.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_code TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL,
                dob TEXT NOT NULL,
                gender TEXT NOT NULL DEFAULT 'Other' CHECK(gender IN ('Male', 'Female', 'Other')),
                address TEXT NOT NULL DEFAULT '',
                department_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                semester INTEGER NOT NULL DEFAULT 1,
                admission_date TEXT NOT NULL,
                academic_year TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active', 'Inactive', 'Graduated', 'Suspended')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE RESTRICT,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE RESTRICT
            )
        """)

        # Migrate any legacy students rows
        if legacy_students_rows:
            default_course = db.execute("SELECT id, department_id FROM courses ORDER BY id ASC LIMIT 1").fetchone()
            for idx, row in enumerate(legacy_students_rows, start=1):
                code = f"STU{1000 + idx}"
                db.execute(
                    """
                    INSERT OR IGNORE INTO students (
                        student_code, name, email, phone, dob, gender, address,
                        department_id, course_id, semester, admission_date, academic_year, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        code, row[1], row[2], "+91-9000000000", "2004-01-01", "Other", "",
                        default_course[1], default_course[0], 1, "2026-08-01", "2026-2027", "Active"
                    )
                )

        # 4. Enrollments
        db.execute("""
            CREATE TABLE IF NOT EXISTS enrollments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                course_id INTEGER NOT NULL,
                semester INTEGER NOT NULL DEFAULT 1,
                enrolled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, course_id),
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
            )
        """)

        # Seed initial students if empty
        if db.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0:
            c1 = db.execute("SELECT id, department_id FROM courses ORDER BY id ASC LIMIT 1").fetchone()
            c2 = db.execute("SELECT id, department_id FROM courses ORDER BY id DESC LIMIT 1").fetchone()
            db.execute(
                """
                INSERT INTO students (
                    student_code, name, email, phone, dob, gender, address,
                    department_id, course_id, semester, admission_date, academic_year, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("STU1001", "Ananya Verma", "ananya.verma@mevi.local", "+91-9876543210", "2005-05-14", "Female", "Bengaluru, India", c1[1], c1[0], 2, "2025-08-01", "2026-2027", "Active")
            )
            s1_id = db.execute("SELECT id FROM students WHERE student_code = 'STU1001'").fetchone()[0]
            db.execute(
                """
                INSERT INTO students (
                    student_code, name, email, phone, dob, gender, address,
                    department_id, course_id, semester, admission_date, academic_year, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("STU1002", "Kabir Patel", "kabir.patel@mevi.local", "+91-9876501234", "2004-11-22", "Male", "Ahmedabad, India", c2[1], c2[0], 4, "2024-08-01", "2026-2027", "Active")
            )
            s2_id = db.execute("SELECT id FROM students WHERE student_code = 'STU1002'").fetchone()[0]
            db.execute("INSERT OR IGNORE INTO enrollments (student_id, course_id, semester) VALUES (?, ?, ?)", (s1_id, c1[0], 2))
            db.execute("INSERT OR IGNORE INTO enrollments (student_id, course_id, semester) VALUES (?, ?, ?)", (s2_id, c2[0], 4))

        # 5. Attendance (preserve legacy employee attendance if present)
        if table_exists(db, "attendance") and "student_id" not in table_columns(db, "attendance"):
            if not table_exists(db, "employee_attendance_legacy"):
                db.execute("ALTER TABLE attendance RENAME TO employee_attendance_legacy")
            else:
                db.execute("DROP TABLE attendance")

        db.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                course_id INTEGER,
                semester INTEGER NOT NULL DEFAULT 1,
                date TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('Present', 'Absent', 'Leave')),
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, date),
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
            )
        """)

        # 6. Examinations & Results
        db.execute("""
            CREATE TABLE IF NOT EXISTS examinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_code TEXT NOT NULL UNIQUE,
                exam_name TEXT NOT NULL,
                course_id INTEGER NOT NULL,
                semester INTEGER NOT NULL,
                exam_date TEXT NOT NULL,
                max_marks REAL NOT NULL DEFAULT 100,
                pass_marks REAL NOT NULL DEFAULT 40,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                examination_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                marks_obtained REAL NOT NULL,
                percentage REAL NOT NULL,
                grade TEXT NOT NULL,
                pass_status TEXT NOT NULL CHECK(pass_status IN ('Pass', 'Fail')),
                remarks TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(examination_id, student_id),
                FOREIGN KEY (examination_id) REFERENCES examinations(id) ON DELETE CASCADE,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
            )
        """)

        # 7. Fee Structures & Fee Payments
        db.execute("""
            CREATE TABLE IF NOT EXISTS fee_structures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                semester INTEGER NOT NULL,
                academic_year TEXT NOT NULL,
                tuition_fee REAL NOT NULL DEFAULT 0,
                lab_fee REAL NOT NULL DEFAULT 0,
                library_fee REAL NOT NULL DEFAULT 0,
                other_fee REAL NOT NULL DEFAULT 0,
                total_fee REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(course_id, semester, academic_year),
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
            )
        """)

        db.execute("""
            CREATE TABLE IF NOT EXISTS fee_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                fee_structure_id INTEGER,
                academic_year TEXT NOT NULL,
                semester INTEGER NOT NULL,
                total_due REAL NOT NULL,
                amount_paid REAL NOT NULL DEFAULT 0,
                balance REAL NOT NULL,
                payment_date TEXT NOT NULL DEFAULT '',
                payment_method TEXT NOT NULL DEFAULT 'Online',
                status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'Partial', 'Paid')),
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(student_id, semester, academic_year),
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE,
                FOREIGN KEY (fee_structure_id) REFERENCES fee_structures(id) ON DELETE SET NULL
            )
        """)

        # 8. Users (migrate from employee users if needed, preserving admin accounts)
        legacy_admins = []
        if table_exists(db, "users") and "student_id" not in table_columns(db, "users"):
            legacy_admins = db.execute(
                "SELECT username, email, password_hash FROM users WHERE role = 'admin'"
            ).fetchall()
            if not table_exists(db, "users_legacy"):
                db.execute("ALTER TABLE users RENAME TO users_legacy")
            else:
                db.execute("DROP TABLE users")

        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'student')),
                student_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE SET NULL
            )
        """)

        for adm in legacy_admins:
            db.execute(
                "INSERT OR IGNORE INTO users (username, email, password_hash, role, student_id) VALUES (?, ?, ?, 'admin', NULL)",
                (adm[0], adm[1], adm[2])
            )

        if db.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0] == 0:
            db.execute(
                "INSERT OR IGNORE INTO users (username, email, password_hash, role, student_id) VALUES (?, ?, ?, 'admin', NULL)",
                ("admin", "admin@mevi.local", generate_password_hash("admin123"))
            )

        if db.execute("SELECT COUNT(*) FROM users WHERE role = 'student'").fetchone()[0] == 0:
            first_stu = db.execute("SELECT id FROM students ORDER BY id ASC LIMIT 1").fetchone()
            stu_id = first_stu[0] if first_stu else None
            db.execute(
                "INSERT OR IGNORE INTO users (username, email, password_hash, role, student_id) VALUES (?, ?, ?, 'student', ?)",
                ("student", "student@mevi.local", generate_password_hash("student123"), stu_id)
            )

        db.execute("PRAGMA foreign_keys = ON")


init_db()


# =====================================
# AUTHENTICATION & AUTHORIZATION
# =====================================

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required."}), 401
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "Authentication required."}), 401
        if session.get("role") != "admin":
            return jsonify({"error": "Administrator privileges required."}), 403
        return fn(*args, **kwargs)
    return wrapper


def get_json_data():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def parse_date(value):
    if not value or not DATE_REGEX.match(value):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "user_id" in session:
            return redirect(url_for("dashboard"))
        return render_template("login.html")

    data = get_json_data() if request.is_json else request.form
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        if request.is_json:
            return jsonify({"error": "Username and password are required."}), 400
        return render_template("login.html", error="Username and password are required.")

    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE LOWER(username) = LOWER(?) OR LOWER(email) = LOWER(?)",
        (username, username)
    ).fetchone()

    if not user or not check_password_hash(user["password_hash"], password):
        if request.is_json:
            return jsonify({"error": "Invalid username or password."}), 401
        return render_template("login.html", error="Invalid username or password.")

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    session["student_id"] = user["student_id"]

    if request.is_json:
        return jsonify({
            "message": "Login successful.",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "student_id": user["student_id"],
            }
        })
    return redirect(url_for("dashboard"))


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    if request.is_json:
        return jsonify({"message": "Logged out successfully."})
    return redirect(url_for("login"))


@app.route("/api/me")
@login_required
def current_user():
    db = get_db()
    stu = None
    if session.get("student_id"):
        row = db.execute(
            """
            SELECT s.*, d.name AS department_name, c.course_name, c.course_code
            FROM students s
            JOIN departments d ON s.department_id = d.id
            JOIN courses c ON s.course_id = c.id
            WHERE s.id = ?
            """,
            (session["student_id"],)
        ).fetchone()
        if row:
            stu = dict(row)

    return jsonify({
        "id": session["user_id"],
        "username": session["username"],
        "role": session["role"],
        "student_id": session.get("student_id"),
        "student": stu
    })


# =====================================
# MAIN PAGES & HEALTH
# =====================================

@app.route("/")
@login_required
def dashboard():
    return render_template(
        "index.html",
        username=session.get("username"),
        role=session.get("role"),
        student_id=session.get("student_id")
    )


@app.route("/health")
def health():
    try:
        db = get_db()
        db.execute("SELECT 1").fetchone()
        db_ok = True
    except sqlite3.Error:
        db_ok = False
    return jsonify({
        "status": "healthy" if db_ok else "degraded",
        "database": "connected" if db_ok else "error",
        "application": "Student Management System"
    }), 200 if db_ok else 500


@app.route("/api/grading-rules")
@login_required
def grading_rules():
    return jsonify(GRADING_SCALE)


# =====================================
# DASHBOARD STATS API
# =====================================

@app.route("/api/dashboard")
@login_required
def dashboard_api():
    db = get_db()
    is_student = session.get("role") == "student" and session.get("student_id")
    stu_id = session.get("student_id")

    total_students = db.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    total_courses = db.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    total_departments = db.execute("SELECT COUNT(*) FROM departments").fetchone()[0]
    total_enrollments = db.execute("SELECT COUNT(*) FROM enrollments").fetchone()[0]

    if is_student:
        att_row = db.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) AS present FROM attendance WHERE student_id = ?",
            (stu_id,)
        ).fetchone()
        fee_row = db.execute(
            "SELECT COALESCE(SUM(amount_paid),0) AS collected, COALESCE(SUM(balance),0) AS pending FROM fee_payments WHERE student_id = ?",
            (stu_id,)
        ).fetchone()
        avg_att = round((att_row["present"] or 0) / att_row["total"] * 100, 1) if att_row["total"] else 0.0
        recent_admissions = [
            dict(r) for r in db.execute(
                """
                SELECT s.id, s.student_code, s.name, s.admission_date, s.semester, s.status, c.course_name
                FROM students s JOIN courses c ON s.course_id = c.id
                WHERE s.id = ?
                """,
                (stu_id,)
            ).fetchall()
        ]
        recent_payments = [
            dict(r) for r in db.execute(
                """
                SELECT fp.*, s.student_code, s.name AS student_name
                FROM fee_payments fp JOIN students s ON fp.student_id = s.id
                WHERE fp.student_id = ?
                ORDER BY fp.id DESC LIMIT 5
                """,
                (stu_id,)
            ).fetchall()
        ]
    else:
        att_row = db.execute(
            "SELECT COUNT(*) AS total, SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) AS present FROM attendance"
        ).fetchone()
        fee_row = db.execute(
            "SELECT COALESCE(SUM(amount_paid),0) AS collected, COALESCE(SUM(balance),0) AS pending FROM fee_payments"
        ).fetchone()
        avg_att = round((att_row["present"] or 0) / att_row["total"] * 100, 1) if att_row["total"] else 0.0
        recent_admissions = [
            dict(r) for r in db.execute(
                """
                SELECT s.id, s.student_code, s.name, s.admission_date, s.semester, s.status, c.course_name
                FROM students s JOIN courses c ON s.course_id = c.id
                ORDER BY s.id DESC LIMIT 5
                """
            ).fetchall()
        ]
        recent_payments = [
            dict(r) for r in db.execute(
                """
                SELECT fp.*, s.student_code, s.name AS student_name
                FROM fee_payments fp JOIN students s ON fp.student_id = s.id
                ORDER BY fp.id DESC LIMIT 5
                """
            ).fetchall()
        ]

    course_distribution = [
        dict(r) for r in db.execute(
            """
            SELECT c.course_code, c.course_name, COUNT(s.id) AS student_count
            FROM courses c LEFT JOIN students s ON s.course_id = c.id
            GROUP BY c.id ORDER BY student_count DESC
            """
        ).fetchall()
    ]

    perf_row = db.execute(
        """
        SELECT COUNT(*) AS total_results,
               COALESCE(AVG(percentage), 0) AS avg_percentage,
               SUM(CASE WHEN pass_status = 'Pass' THEN 1 ELSE 0 END) AS pass_count
        FROM results
        """ + (" WHERE student_id = ?" if is_student else ""),
        (stu_id,) if is_student else ()
    ).fetchone()

    total_res = perf_row["total_results"] or 0
    pass_rate = round((perf_row["pass_count"] or 0) / total_res * 100, 1) if total_res else 0.0

    return jsonify({
        "total_students": total_students,
        "total_courses": total_courses,
        "total_departments": total_departments,
        "total_enrollments": total_enrollments,
        "average_attendance": avg_att,
        "total_fee_collection": round(float(fee_row["collected"]), 2),
        "pending_fee_payments": round(float(fee_row["pending"]), 2),
        "recent_admissions": recent_admissions,
        "recent_payments": recent_payments,
        "course_distribution": course_distribution,
        "academic_overview": {
            "total_results": total_res,
            "average_percentage": round(float(perf_row["avg_percentage"]), 1),
            "pass_rate": pass_rate
        }
    })


# =====================================
# STUDENT MANAGEMENT API
# =====================================

@app.route("/api/students", methods=["GET"])
@login_required
def list_students():
    db = get_db()
    search = (request.args.get("search") or "").strip().lower()
    course_id = (request.args.get("course_id") or "").strip()
    department_id = (request.args.get("department_id") or "").strip()
    semester = (request.args.get("semester") or "").strip()
    sort = request.args.get("sort", "newest")

    query = """
        SELECT s.*, d.name AS department_name, d.code AS department_code,
               c.course_name, c.course_code
        FROM students s
        JOIN departments d ON s.department_id = d.id
        JOIN courses c ON s.course_id = c.id
        WHERE 1=1
    """
    params = []

    if session.get("role") == "student":
        if not session.get("student_id"):
            return jsonify([])
        query += " AND s.id = ?"
        params.append(session["student_id"])

    if search:
        like = f"%{search}%"
        query += " AND (LOWER(s.name) LIKE ? OR LOWER(s.student_code) LIKE ? OR LOWER(s.email) LIKE ?)"
        params.extend([like, like, like])
    if course_id:
        query += " AND s.course_id = ?"
        params.append(course_id)
    if department_id:
        query += " AND s.department_id = ?"
        params.append(department_id)
    if semester:
        query += " AND s.semester = ?"
        params.append(semester)

    sort_map = {
        "newest": "s.id DESC",
        "name_asc": "LOWER(s.name) ASC",
        "name_desc": "LOWER(s.name) DESC",
        "code_asc": "LOWER(s.student_code) ASC",
        "semester_asc": "s.semester ASC"
    }
    query += f" ORDER BY {sort_map.get(sort, 's.id DESC')}"

    return jsonify([dict(r) for r in db.execute(query, params).fetchall()])


@app.route("/api/students/<int:stu_id>", methods=["GET"])
@login_required
def get_student(stu_id):
    if session.get("role") == "student" and session.get("student_id") != stu_id:
        return jsonify({"error": "Access denied to other students' records."}), 403

    db = get_db()
    row = db.execute(
        """
        SELECT s.*, d.name AS department_name, c.course_name, c.course_code
        FROM students s
        JOIN departments d ON s.department_id = d.id
        JOIN courses c ON s.course_id = c.id
        WHERE s.id = ?
        """,
        (stu_id,)
    ).fetchone()
    if not row:
        return jsonify({"error": "Student not found."}), 404

    att = db.execute(
        """
        SELECT COUNT(*) AS total_days,
               SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) AS present_days,
               SUM(CASE WHEN status='Absent' THEN 1 ELSE 0 END) AS absent_days,
               SUM(CASE WHEN status='Leave' THEN 1 ELSE 0 END) AS leave_days
        FROM attendance WHERE student_id = ?
        """,
        (stu_id,)
    ).fetchone()
    total_days = att["total_days"] or 0
    present_days = att["present_days"] or 0

    enrollments = [
        dict(r) for r in db.execute(
            """
            SELECT e.*, c.course_code, c.course_name
            FROM enrollments e JOIN courses c ON e.course_id = c.id
            WHERE e.student_id = ?
            """,
            (stu_id,)
        ).fetchall()
    ]

    results = [
        dict(r) for r in db.execute(
            """
            SELECT r.*, ex.exam_code, ex.exam_name, ex.max_marks
            FROM results r JOIN examinations ex ON r.examination_id = ex.id
            WHERE r.student_id = ? ORDER BY ex.exam_date DESC
            """,
            (stu_id,)
        ).fetchall()
    ]

    fees = [
        dict(r) for r in db.execute(
            "SELECT * FROM fee_payments WHERE student_id = ? ORDER BY semester ASC",
            (stu_id,)
        ).fetchall()
    ]

    res = dict(row)
    res["attendance_summary"] = {
        "total_days": total_days,
        "present_days": present_days,
        "absent_days": att["absent_days"] or 0,
        "leave_days": att["leave_days"] or 0,
        "attendance_percentage": round((present_days / total_days) * 100, 1) if total_days else 0.0
    }
    res["enrollments"] = enrollments
    res["results"] = results
    res["fees"] = fees
    return jsonify(res)


@app.route("/api/students", methods=["POST"])
@admin_required
def create_student():
    data = get_json_data()
    student_code = (data.get("student_code") or "").strip().upper()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    dob = (data.get("dob") or "").strip()
    gender = (data.get("gender") or "Other").strip()
    address = (data.get("address") or "").strip()
    department_id = data.get("department_id")
    course_id = data.get("course_id")
    admission_date = (data.get("admission_date") or "").strip()
    academic_year = (data.get("academic_year") or "").strip()
    status = (data.get("status") or "Active").strip()

    try:
        semester = int(data.get("semester", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "Semester must be an integer."}), 400

    if not all([student_code, name, email, phone, dob, department_id, course_id, admission_date, academic_year]):
        return jsonify({"error": "All required student fields must be provided."}), 400
    if not EMAIL_REGEX.match(email):
        return jsonify({"error": "Invalid email address."}), 400
    if not parse_date(dob) or not parse_date(admission_date):
        return jsonify({"error": "Dates must be in YYYY-MM-DD format."}), 400
    if gender not in ("Male", "Female", "Other"):
        return jsonify({"error": "Invalid gender."}), 400
    if status not in ("Active", "Inactive", "Graduated", "Suspended"):
        return jsonify({"error": "Invalid student status."}), 400
    if semester < 1:
        return jsonify({"error": "Semester must be >= 1."}), 400

    db = get_db()
    if not db.execute("SELECT id FROM departments WHERE id = ?", (department_id,)).fetchone():
        return jsonify({"error": "Selected department does not exist."}), 400
    if not db.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone():
        return jsonify({"error": "Selected course does not exist."}), 400

    try:
        cur = db.execute(
            """
            INSERT INTO students (
                student_code, name, email, phone, dob, gender, address,
                department_id, course_id, semester, admission_date, academic_year, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (student_code, name, email, phone, dob, gender, address, department_id, course_id, semester, admission_date, academic_year, status)
        )
        stu_id = cur.lastrowid
        db.execute(
            "INSERT OR IGNORE INTO enrollments (student_id, course_id, semester) VALUES (?, ?, ?)",
            (stu_id, course_id, semester)
        )
        db.commit()
        return jsonify({"message": "Student added successfully.", "id": stu_id}), 201
    except sqlite3.IntegrityError as exc:
        msg = str(exc).lower()
        if "student_code" in msg:
            return jsonify({"error": f"Student ID '{student_code}' already exists."}), 409
        if "email" in msg:
            return jsonify({"error": f"Email '{email}' is already registered."}), 409
        return jsonify({"error": "Database constraint error."}), 400


@app.route("/api/students/<int:stu_id>", methods=["PUT"])
@admin_required
def update_student(stu_id):
    db = get_db()
    existing = db.execute("SELECT * FROM students WHERE id = ?", (stu_id,)).fetchone()
    if not existing:
        return jsonify({"error": "Student not found."}), 404

    data = get_json_data()
    student_code = (data.get("student_code") or existing["student_code"]).strip().upper()
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or "").strip()
    dob = (data.get("dob") or "").strip()
    gender = (data.get("gender") or "Other").strip()
    address = (data.get("address") or "").strip()
    department_id = data.get("department_id")
    course_id = data.get("course_id")
    admission_date = (data.get("admission_date") or "").strip()
    academic_year = (data.get("academic_year") or "").strip()
    status = (data.get("status") or "Active").strip()

    try:
        semester = int(data.get("semester", 1))
    except (TypeError, ValueError):
        return jsonify({"error": "Semester must be an integer."}), 400

    if not all([student_code, name, email, phone, dob, department_id, course_id, admission_date, academic_year]):
        return jsonify({"error": "All required student fields must be provided."}), 400
    if not EMAIL_REGEX.match(email):
        return jsonify({"error": "Invalid email address."}), 400
    if not parse_date(dob) or not parse_date(admission_date):
        return jsonify({"error": "Dates must be in YYYY-MM-DD format."}), 400

    try:
        db.execute(
            """
            UPDATE students
            SET student_code=?, name=?, email=?, phone=?, dob=?, gender=?, address=?,
                department_id=?, course_id=?, semester=?, admission_date=?, academic_year=?, status=?
            WHERE id=?
            """,
            (student_code, name, email, phone, dob, gender, address, department_id, course_id, semester, admission_date, academic_year, status, stu_id)
        )
        db.commit()
        return jsonify({"message": "Student updated successfully."})
    except sqlite3.IntegrityError as exc:
        msg = str(exc).lower()
        if "student_code" in msg:
            return jsonify({"error": f"Student ID '{student_code}' already exists."}), 409
        if "email" in msg:
            return jsonify({"error": f"Email '{email}' is already registered."}), 409
        return jsonify({"error": "Database constraint error."}), 400


@app.route("/api/students/<int:stu_id>", methods=["DELETE"])
@admin_required
def delete_student(stu_id):
    db = get_db()
    existing = db.execute("SELECT id, name FROM students WHERE id = ?", (stu_id,)).fetchone()
    if not existing:
        return jsonify({"error": "Student not found."}), 404
    db.execute("DELETE FROM students WHERE id = ?", (stu_id,))
    db.commit()
    return jsonify({"message": f"Student '{existing['name']}' deleted successfully."})


# =====================================
# DEPARTMENT MANAGEMENT API
# =====================================

@app.route("/api/departments", methods=["GET"])
@login_required
def list_departments():
    db = get_db()
    rows = db.execute(
        """
        SELECT d.*,
               COUNT(DISTINCT s.id) AS student_count,
               COUNT(DISTINCT c.id) AS course_count
        FROM departments d
        LEFT JOIN students s ON s.department_id = d.id
        LEFT JOIN courses c ON c.department_id = d.id
        GROUP BY d.id
        ORDER BY d.name ASC
        """
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/departments/<int:dept_id>", methods=["GET"])
@login_required
def get_department(dept_id):
    db = get_db()
    dept = db.execute(
        """
        SELECT d.*, COUNT(DISTINCT s.id) AS student_count, COUNT(DISTINCT c.id) AS course_count
        FROM departments d
        LEFT JOIN students s ON s.department_id = d.id
        LEFT JOIN courses c ON c.department_id = d.id
        WHERE d.id = ? GROUP BY d.id
        """,
        (dept_id,)
    ).fetchone()
    if not dept:
        return jsonify({"error": "Department not found."}), 404

    courses = [
        dict(r) for r in db.execute(
            "SELECT id, course_code, course_name, duration, num_semesters FROM courses WHERE department_id = ?",
            (dept_id,)
        ).fetchall()
    ]
    res = dict(dept)
    res["courses"] = courses
    return jsonify(res)


@app.route("/api/departments", methods=["POST"])
@admin_required
def create_department():
    data = get_json_data()
    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip().upper()
    manager_name = (data.get("manager_name") or "").strip()
    description = (data.get("description") or "").strip()
    if not name or not code:
        return jsonify({"error": "Department name and code are required."}), 400

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO departments (name, code, manager_name, description) VALUES (?, ?, ?, ?)",
            (name, code, manager_name, description)
        )
        db.commit()
        return jsonify({"message": "Department created successfully.", "id": cur.lastrowid}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Department '{name}' or code '{code}' already exists."}), 409


@app.route("/api/departments/<int:dept_id>", methods=["PUT"])
@admin_required
def update_department(dept_id):
    db = get_db()
    if not db.execute("SELECT id FROM departments WHERE id = ?", (dept_id,)).fetchone():
        return jsonify({"error": "Department not found."}), 404
    data = get_json_data()
    name = (data.get("name") or "").strip()
    code = (data.get("code") or "").strip().upper()
    manager_name = (data.get("manager_name") or "").strip()
    description = (data.get("description") or "").strip()
    if not name or not code:
        return jsonify({"error": "Department name and code are required."}), 400

    try:
        db.execute(
            "UPDATE departments SET name=?, code=?, manager_name=?, description=? WHERE id=?",
            (name, code, manager_name, description, dept_id)
        )
        db.commit()
        return jsonify({"message": "Department updated successfully."})
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Department '{name}' or code '{code}' already exists."}), 409


@app.route("/api/departments/<int:dept_id>", methods=["DELETE"])
@admin_required
def delete_department(dept_id):
    db = get_db()
    dept = db.execute("SELECT id, name FROM departments WHERE id = ?", (dept_id,)).fetchone()
    if not dept:
        return jsonify({"error": "Department not found."}), 404

    stu_count = db.execute("SELECT COUNT(*) FROM students WHERE department_id = ?", (dept_id,)).fetchone()[0]
    course_count = db.execute("SELECT COUNT(*) FROM courses WHERE department_id = ?", (dept_id,)).fetchone()[0]
    if stu_count > 0 or course_count > 0:
        return jsonify({
            "error": f"Cannot delete '{dept['name']}' while {course_count} course(s) and {stu_count} student(s) are assigned."
        }), 409

    db.execute("DELETE FROM departments WHERE id = ?", (dept_id,))
    db.commit()
    return jsonify({"message": f"Department '{dept['name']}' deleted successfully."})


@app.route("/api/departments/<int:dept_id>/assign-course", methods=["POST"])
@admin_required
def assign_course_department(dept_id):
    db = get_db()
    dept = db.execute("SELECT id, name FROM departments WHERE id = ?", (dept_id,)).fetchone()
    if not dept:
        return jsonify({"error": "Department not found."}), 404
    course_id = get_json_data().get("course_id")
    course = db.execute("SELECT id, course_name FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        return jsonify({"error": "Course not found."}), 404
    db.execute("UPDATE courses SET department_id = ? WHERE id = ?", (dept_id, course_id))
    db.commit()
    return jsonify({"message": f"{course['course_name']} assigned to {dept['name']}."})


# =====================================
# COURSE & ENROLLMENT MANAGEMENT API
# =====================================

@app.route("/api/courses", methods=["GET"])
@login_required
def list_courses():
    db = get_db()
    search = (request.args.get("search") or "").strip().lower()
    department_id = (request.args.get("department_id") or "").strip()

    query = """
        SELECT c.*, d.name AS department_name, d.code AS department_code,
               COUNT(DISTINCT e.student_id) AS enrolled_count
        FROM courses c
        JOIN departments d ON c.department_id = d.id
        LEFT JOIN enrollments e ON e.course_id = c.id
        WHERE 1=1
    """
    params = []
    if search:
        like = f"%{search}%"
        query += " AND (LOWER(c.course_name) LIKE ? OR LOWER(c.course_code) LIKE ?)"
        params.extend([like, like])
    if department_id:
        query += " AND c.department_id = ?"
        params.append(department_id)

    query += " GROUP BY c.id ORDER BY c.course_code ASC"
    return jsonify([dict(r) for r in db.execute(query, params).fetchall()])


@app.route("/api/courses/<int:course_id>", methods=["GET"])
@login_required
def get_course(course_id):
    db = get_db()
    course = db.execute(
        """
        SELECT c.*, d.name AS department_name, COUNT(DISTINCT e.student_id) AS enrolled_count
        FROM courses c
        JOIN departments d ON c.department_id = d.id
        LEFT JOIN enrollments e ON e.course_id = c.id
        WHERE c.id = ? GROUP BY c.id
        """,
        (course_id,)
    ).fetchone()
    if not course:
        return jsonify({"error": "Course not found."}), 404

    if session.get("role") == "student":
        students = []
    else:
        students = [
            dict(r) for r in db.execute(
                """
                SELECT s.id, s.student_code, s.name, s.semester, s.status
                FROM enrollments e JOIN students s ON e.student_id = s.id
                WHERE e.course_id = ? ORDER BY s.name ASC
                """,
                (course_id,)
            ).fetchall()
        ]
    res = dict(course)
    res["enrolled_students"] = students
    return jsonify(res)


@app.route("/api/courses", methods=["POST"])
@admin_required
def create_course():
    data = get_json_data()
    course_code = (data.get("course_code") or "").strip().upper()
    course_name = (data.get("course_name") or "").strip()
    department_id = data.get("department_id")
    duration = (data.get("duration") or "4 Years").strip()
    description = (data.get("description") or "").strip()
    try:
        num_semesters = int(data.get("num_semesters", 8))
    except (TypeError, ValueError):
        return jsonify({"error": "Number of semesters must be an integer."}), 400

    if not all([course_code, course_name, department_id]) or num_semesters < 1:
        return jsonify({"error": "Course code, name, department, and valid semesters are required."}), 400

    db = get_db()
    if not db.execute("SELECT id FROM departments WHERE id = ?", (department_id,)).fetchone():
        return jsonify({"error": "Selected department does not exist."}), 400

    try:
        cur = db.execute(
            """
            INSERT INTO courses (course_code, course_name, department_id, duration, num_semesters, description)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (course_code, course_name, department_id, duration, num_semesters, description)
        )
        db.commit()
        return jsonify({"message": "Course created successfully.", "id": cur.lastrowid}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Course code '{course_code}' already exists."}), 409


@app.route("/api/courses/<int:course_id>", methods=["PUT"])
@admin_required
def update_course(course_id):
    db = get_db()
    if not db.execute("SELECT id FROM courses WHERE id = ?", (course_id,)).fetchone():
        return jsonify({"error": "Course not found."}), 404
    data = get_json_data()
    course_code = (data.get("course_code") or "").strip().upper()
    course_name = (data.get("course_name") or "").strip()
    department_id = data.get("department_id")
    duration = (data.get("duration") or "4 Years").strip()
    description = (data.get("description") or "").strip()
    try:
        num_semesters = int(data.get("num_semesters", 8))
    except (TypeError, ValueError):
        return jsonify({"error": "Number of semesters must be an integer."}), 400

    if not all([course_code, course_name, department_id]) or num_semesters < 1:
        return jsonify({"error": "Valid course details are required."}), 400

    try:
        db.execute(
            """
            UPDATE courses SET course_code=?, course_name=?, department_id=?, duration=?, num_semesters=?, description=?
            WHERE id=?
            """,
            (course_code, course_name, department_id, duration, num_semesters, description, course_id)
        )
        db.commit()
        return jsonify({"message": "Course updated successfully."})
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Course code '{course_code}' already exists."}), 409


@app.route("/api/courses/<int:course_id>", methods=["DELETE"])
@admin_required
def delete_course(course_id):
    db = get_db()
    course = db.execute("SELECT id, course_name FROM courses WHERE id = ?", (course_id,)).fetchone()
    if not course:
        return jsonify({"error": "Course not found."}), 404
    stu_count = db.execute("SELECT COUNT(*) FROM students WHERE course_id = ?", (course_id,)).fetchone()[0]
    if stu_count > 0:
        return jsonify({"error": f"Cannot delete '{course['course_name']}' while {stu_count} student(s) are enrolled in it."}), 409
    db.execute("DELETE FROM courses WHERE id = ?", (course_id,))
    db.commit()
    return jsonify({"message": f"Course '{course['course_name']}' deleted successfully."})


@app.route("/api/enrollments", methods=["GET"])
@login_required
def list_enrollments():
    db = get_db()
    query = """
        SELECT e.*, s.student_code, s.name AS student_name, c.course_code, c.course_name
        FROM enrollments e
        JOIN students s ON e.student_id = s.id
        JOIN courses c ON e.course_id = c.id
    """
    params = []
    if session.get("role") == "student":
        query += " WHERE e.student_id = ?"
        params.append(session.get("student_id"))
    query += " ORDER BY e.id DESC"
    return jsonify([dict(r) for r in db.execute(query, params).fetchall()])


@app.route("/api/enrollments", methods=["POST"])
@admin_required
def create_enrollment():
    data = get_json_data()
    student_id = data.get("student_id")
    course_id = data.get("course_id")
    semester = int(data.get("semester", 1))
    if not student_id or not course_id:
        return jsonify({"error": "Student and course are required."}), 400

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO enrollments (student_id, course_id, semester) VALUES (?, ?, ?)",
            (student_id, course_id, semester)
        )
        db.commit()
        return jsonify({"message": "Student enrolled in course.", "id": cur.lastrowid}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Student is already enrolled in this course."}), 409


@app.route("/api/enrollments/<int:enroll_id>", methods=["DELETE"])
@admin_required
def delete_enrollment(enroll_id):
    db = get_db()
    db.execute("DELETE FROM enrollments WHERE id = ?", (enroll_id,))
    db.commit()
    return jsonify({"message": "Enrollment removed."})


# =====================================
# STUDENT ATTENDANCE MANAGEMENT API
# =====================================

@app.route("/api/attendance", methods=["GET"])
@login_required
def list_attendance():
    db = get_db()
    student_id = (request.args.get("student_id") or "").strip()
    course_id = (request.args.get("course_id") or "").strip()
    semester = (request.args.get("semester") or "").strip()
    date_filter = (request.args.get("date") or "").strip()

    query = """
        SELECT a.*, s.student_code, s.name AS student_name, c.course_name, c.course_code
        FROM attendance a
        JOIN students s ON a.student_id = s.id
        LEFT JOIN courses c ON a.course_id = c.id
        WHERE 1=1
    """
    params = []

    if session.get("role") == "student":
        query += " AND a.student_id = ?"
        params.append(session.get("student_id"))
    else:
        if student_id:
            query += " AND a.student_id = ?"
            params.append(student_id)
        if course_id:
            query += " AND a.course_id = ?"
            params.append(course_id)
        if semester:
            query += " AND a.semester = ?"
            params.append(semester)

    if date_filter:
        query += " AND a.date = ?"
        params.append(date_filter)

    query += " ORDER BY a.date DESC, a.id DESC"
    records = [dict(r) for r in db.execute(query, params).fetchall()]

    sum_query = """
        SELECT s.id AS student_id, s.student_code, s.name AS student_name,
               COUNT(a.id) AS total_days,
               SUM(CASE WHEN a.status = 'Present' THEN 1 ELSE 0 END) AS present_days,
               SUM(CASE WHEN a.status = 'Absent' THEN 1 ELSE 0 END) AS absent_days,
               SUM(CASE WHEN a.status = 'Leave' THEN 1 ELSE 0 END) AS leave_days
        FROM students s
        LEFT JOIN attendance a ON a.student_id = s.id
        WHERE 1=1
    """
    sum_params = []
    if session.get("role") == "student":
        sum_query += " AND s.id = ?"
        sum_params.append(session.get("student_id"))
    elif student_id:
        sum_query += " AND s.id = ?"
        sum_params.append(student_id)
    sum_query += " GROUP BY s.id ORDER BY s.name ASC"

    summary = []
    for r in db.execute(sum_query, sum_params).fetchall():
        item = dict(r)
        total = item["total_days"] or 0
        present = item["present_days"] or 0
        item["present_days"] = present
        item["absent_days"] = item["absent_days"] or 0
        item["leave_days"] = item["leave_days"] or 0
        item["attendance_percentage"] = round((present / total) * 100, 1) if total > 0 else 0.0
        summary.append(item)

    return jsonify({"records": records, "summary": summary})


@app.route("/api/attendance", methods=["POST"])
@admin_required
def record_attendance():
    data = get_json_data()
    student_id = data.get("student_id")
    att_date = (data.get("date") or "").strip()
    status = (data.get("status") or "").strip()
    notes = (data.get("notes") or "").strip()

    if not student_id or not att_date or status not in ("Present", "Absent", "Leave"):
        return jsonify({"error": "Student, valid date, and status (Present/Absent/Leave) are required."}), 400
    if not parse_date(att_date):
        return jsonify({"error": "Date must be in YYYY-MM-DD format."}), 400

    db = get_db()
    stu = db.execute("SELECT id, name, course_id, semester FROM students WHERE id = ?", (student_id,)).fetchone()
    if not stu:
        return jsonify({"error": "Student not found."}), 404

    course_id = data.get("course_id") or stu["course_id"]
    semester = int(data.get("semester") or stu["semester"])

    try:
        cur = db.execute(
            "INSERT INTO attendance (student_id, course_id, semester, date, status, notes) VALUES (?, ?, ?, ?, ?, ?)",
            (student_id, course_id, semester, att_date, status, notes)
        )
        db.commit()
        return jsonify({"message": f"Attendance recorded for {stu['name']} on {att_date}.", "id": cur.lastrowid}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Attendance for {stu['name']} on {att_date} already exists."}), 409


@app.route("/api/attendance/<int:att_id>", methods=["DELETE"])
@admin_required
def delete_attendance(att_id):
    db = get_db()
    db.execute("DELETE FROM attendance WHERE id = ?", (att_id,))
    db.commit()
    return jsonify({"message": "Attendance record deleted."})


# =====================================
# EXAMINATION & RESULTS MANAGEMENT API
# =====================================

@app.route("/api/examinations", methods=["GET"])
@login_required
def list_examinations():
    db = get_db()
    rows = db.execute(
        """
        SELECT ex.*, c.course_code, c.course_name
        FROM examinations ex
        JOIN courses c ON ex.course_id = c.id
        ORDER BY ex.exam_date DESC, ex.id DESC
        """
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/examinations", methods=["POST"])
@admin_required
def create_examination():
    data = get_json_data()
    exam_code = (data.get("exam_code") or "").strip().upper()
    exam_name = (data.get("exam_name") or "").strip()
    course_id = data.get("course_id")
    exam_date = (data.get("exam_date") or "").strip()

    try:
        semester = int(data.get("semester", 1))
        max_marks = float(data.get("max_marks", 100))
        pass_marks = float(data.get("pass_marks", 40))
    except (TypeError, ValueError):
        return jsonify({"error": "Semester and marks must be valid numbers."}), 400

    if not all([exam_code, exam_name, course_id, exam_date]) or not parse_date(exam_date):
        return jsonify({"error": "Valid exam code, name, course, and date are required."}), 400
    if max_marks <= 0 or pass_marks < 0 or pass_marks > max_marks:
        return jsonify({"error": "Pass marks must be between 0 and max marks."}), 400

    db = get_db()
    try:
        cur = db.execute(
            """
            INSERT INTO examinations (exam_code, exam_name, course_id, semester, exam_date, max_marks, pass_marks)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (exam_code, exam_name, course_id, semester, exam_date, max_marks, pass_marks)
        )
        db.commit()
        return jsonify({"message": "Examination created successfully.", "id": cur.lastrowid}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Exam code '{exam_code}' already exists."}), 409


@app.route("/api/examinations/<int:exam_id>", methods=["DELETE"])
@admin_required
def delete_examination(exam_id):
    db = get_db()
    db.execute("DELETE FROM examinations WHERE id = ?", (exam_id,))
    db.commit()
    return jsonify({"message": "Examination deleted."})


@app.route("/api/results", methods=["GET"])
@login_required
def list_results():
    db = get_db()
    student_id = (request.args.get("student_id") or "").strip()
    exam_id = (request.args.get("examination_id") or "").strip()

    query = """
        SELECT r.*, s.student_code, s.name AS student_name,
               ex.exam_code, ex.exam_name, ex.max_marks, ex.pass_marks, ex.semester,
               c.course_name
        FROM results r
        JOIN students s ON r.student_id = s.id
        JOIN examinations ex ON r.examination_id = ex.id
        JOIN courses c ON ex.course_id = c.id
        WHERE 1=1
    """
    params = []
    if session.get("role") == "student":
        query += " AND r.student_id = ?"
        params.append(session.get("student_id"))
    elif student_id:
        query += " AND r.student_id = ?"
        params.append(student_id)

    if exam_id:
        query += " AND r.examination_id = ?"
        params.append(exam_id)

    query += " ORDER BY r.id DESC"
    return jsonify([dict(r) for r in db.execute(query, params).fetchall()])


@app.route("/api/results", methods=["POST"])
@admin_required
def save_result():
    data = get_json_data()
    examination_id = data.get("examination_id")
    student_id = data.get("student_id")
    remarks = (data.get("remarks") or "").strip()
    try:
        marks_obtained = float(data.get("marks_obtained"))
    except (TypeError, ValueError):
        return jsonify({"error": "Marks obtained must be a valid number."}), 400

    db = get_db()
    exam = db.execute("SELECT * FROM examinations WHERE id = ?", (examination_id,)).fetchone()
    stu = db.execute("SELECT id, name FROM students WHERE id = ?", (student_id,)).fetchone()
    if not exam or not stu:
        return jsonify({"error": "Valid examination and student are required."}), 400
    if marks_obtained < 0 or marks_obtained > exam["max_marks"]:
        return jsonify({"error": f"Marks must be between 0 and {exam['max_marks']}."}), 400

    percentage = round((marks_obtained / exam["max_marks"]) * 100.0, 2)
    grade, pass_status = compute_grade(percentage, marks_obtained, exam["pass_marks"])

    existing = db.execute(
        "SELECT id FROM results WHERE examination_id = ? AND student_id = ?",
        (examination_id, student_id)
    ).fetchone()

    if existing:
        db.execute(
            """
            UPDATE results SET marks_obtained=?, percentage=?, grade=?, pass_status=?, remarks=?
            WHERE id=?
            """,
            (marks_obtained, percentage, grade, pass_status, remarks, existing["id"])
        )
        db.commit()
        return jsonify({"message": "Result updated successfully.", "id": existing["id"], "grade": grade, "pass_status": pass_status})

    cur = db.execute(
        """
        INSERT INTO results (examination_id, student_id, marks_obtained, percentage, grade, pass_status, remarks)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (examination_id, student_id, marks_obtained, percentage, grade, pass_status, remarks)
    )
    db.commit()
    return jsonify({"message": "Result recorded successfully.", "id": cur.lastrowid, "grade": grade, "pass_status": pass_status}), 201


@app.route("/api/results/<int:result_id>", methods=["DELETE"])
@admin_required
def delete_result(result_id):
    db = get_db()
    db.execute("DELETE FROM results WHERE id = ?", (result_id,))
    db.commit()
    return jsonify({"message": "Result deleted."})


# =====================================
# FEES MANAGEMENT API
# =====================================

@app.route("/api/fee-structures", methods=["GET"])
@login_required
def list_fee_structures():
    db = get_db()
    rows = db.execute(
        """
        SELECT fs.*, c.course_code, c.course_name
        FROM fee_structures fs
        JOIN courses c ON fs.course_id = c.id
        ORDER BY fs.academic_year DESC, c.course_code ASC, fs.semester ASC
        """
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/fee-structures", methods=["POST"])
@admin_required
def create_fee_structure():
    data = get_json_data()
    course_id = data.get("course_id")
    academic_year = (data.get("academic_year") or "").strip()
    try:
        semester = int(data.get("semester", 1))
        tuition = float(data.get("tuition_fee", 0))
        lab = float(data.get("lab_fee", 0))
        library = float(data.get("library_fee", 0))
        other = float(data.get("other_fee", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Fee amounts and semester must be valid numbers."}), 400

    if not course_id or not academic_year or semester < 1 or any(v < 0 for v in [tuition, lab, library, other]):
        return jsonify({"error": "Valid course, academic year, semester, and non-negative fees are required."}), 400

    total_fee = round(tuition + lab + library + other, 2)
    if total_fee <= 0:
        return jsonify({"error": "Total fee must be greater than 0."}), 400

    db = get_db()
    try:
        cur = db.execute(
            """
            INSERT INTO fee_structures (course_id, semester, academic_year, tuition_fee, lab_fee, library_fee, other_fee, total_fee)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (course_id, semester, academic_year, tuition, lab, library, other, total_fee)
        )
        db.commit()
        return jsonify({"message": "Fee structure created.", "id": cur.lastrowid, "total_fee": total_fee}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Fee structure for this course, semester, and academic year already exists."}), 409


@app.route("/api/fee-payments", methods=["GET"])
@login_required
def list_fee_payments():
    db = get_db()
    search = (request.args.get("search") or "").strip().lower()
    status_filter = (request.args.get("status") or "").strip()

    query = """
        SELECT fp.*, s.student_code, s.name AS student_name, c.course_name
        FROM fee_payments fp
        JOIN students s ON fp.student_id = s.id
        JOIN courses c ON s.course_id = c.id
        WHERE 1=1
    """
    params = []
    if session.get("role") == "student":
        query += " AND fp.student_id = ?"
        params.append(session.get("student_id"))
    elif search:
        like = f"%{search}%"
        query += " AND (LOWER(s.student_code) LIKE ? OR LOWER(s.name) LIKE ?)"
        params.extend([like, like])

    if status_filter:
        query += " AND fp.status = ?"
        params.append(status_filter)

    query += " ORDER BY fp.id DESC"
    return jsonify([dict(r) for r in db.execute(query, params).fetchall()])


@app.route("/api/fee-payments", methods=["POST"])
@admin_required
def create_or_record_fee():
    data = get_json_data()
    student_id = data.get("student_id")
    academic_year = (data.get("academic_year") or "").strip()
    payment_method = (data.get("payment_method") or "Online").strip()
    payment_date = (data.get("payment_date") or datetime.utcnow().strftime("%Y-%m-%d")).strip()
    notes = (data.get("notes") or "").strip()

    try:
        semester = int(data.get("semester", 1))
        total_due = float(data.get("total_due", 0))
        amount_paid = float(data.get("amount_paid", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Amounts and semester must be valid numbers."}), 400

    if not student_id or not academic_year or total_due <= 0 or amount_paid < 0:
        return jsonify({"error": "Valid student, academic year, and amounts are required."}), 400
    if amount_paid > total_due:
        return jsonify({"error": "Amount paid cannot exceed total due."}), 400

    balance = round(total_due - amount_paid, 2)
    status = "Paid" if balance == 0 else ("Partial" if amount_paid > 0 else "Pending")

    db = get_db()
    stu = db.execute("SELECT id, name, course_id FROM students WHERE id = ?", (student_id,)).fetchone()
    if not stu:
        return jsonify({"error": "Student not found."}), 404

    fs = db.execute(
        "SELECT id FROM fee_structures WHERE course_id = ? AND semester = ? AND academic_year = ?",
        (stu["course_id"], semester, academic_year)
    ).fetchone()
    fs_id = fs["id"] if fs else None

    try:
        cur = db.execute(
            """
            INSERT INTO fee_payments (
                student_id, fee_structure_id, academic_year, semester,
                total_due, amount_paid, balance, payment_date, payment_method, status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (student_id, fs_id, academic_year, semester, total_due, amount_paid, balance, payment_date, payment_method, status, notes)
        )
        db.commit()
        return jsonify({"message": f"Fee record created for {stu['name']}.", "id": cur.lastrowid, "balance": balance, "status": status}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": f"Fee record for {stu['name']} in Sem {semester} ({academic_year}) already exists."}), 409


@app.route("/api/fee-payments/<int:fee_id>/pay", methods=["PUT"])
@admin_required
def pay_fee_installment(fee_id):
    db = get_db()
    existing = db.execute("SELECT * FROM fee_payments WHERE id = ?", (fee_id,)).fetchone()
    if not existing:
        return jsonify({"error": "Fee record not found."}), 404

    data = get_json_data()
    try:
        add_amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Payment amount must be a valid number."}), 400

    if add_amount <= 0 or add_amount > existing["balance"]:
        return jsonify({"error": f"Payment must be > 0 and <= remaining balance ({existing['balance']})."}), 400

    new_paid = round(existing["amount_paid"] + add_amount, 2)
    new_balance = round(existing["total_due"] - new_paid, 2)
    new_status = "Paid" if new_balance == 0 else "Partial"
    pay_date = datetime.utcnow().strftime("%Y-%m-%d")

    db.execute(
        "UPDATE fee_payments SET amount_paid=?, balance=?, status=?, payment_date=? WHERE id=?",
        (new_paid, new_balance, new_status, pay_date, fee_id)
    )
    db.commit()
    return jsonify({"message": "Payment recorded.", "balance": new_balance, "status": new_status})


@app.route("/api/fee-payments/<int:fee_id>", methods=["DELETE"])
@admin_required
def delete_fee_payment(fee_id):
    db = get_db()
    db.execute("DELETE FROM fee_payments WHERE id = ?", (fee_id,))
    db.commit()
    return jsonify({"message": "Fee record deleted."})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
