/* =====================================
   CAMPUSFLOW - STUDENT MANAGEMENT SYSTEM
   ===================================== */

const USER_ROLE = document.body.dataset.role || "student";
const IS_ADMIN = USER_ROLE === "admin";

let allDepartments = [];
let allCourses = [];
let allStudents = [];
let allExams = [];
let allFeeStructures = [];

function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[char]);
}

function formatINR(amount) {
    const num = Number(amount || 0);
    return "₹" + num.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function showToast(message, type = "success") {
    const container = document.getElementById("toastContainer");
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3800);
}

async function apiFetch(url, options = {}) {
    const config = {
        headers: { "Content-Type": "application/json" },
        ...options
    };
    const res = await fetch(url, config);
    if (res.status === 401) {
        window.location.href = "/login";
        throw new Error("Session expired.");
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        throw new Error(data.error || `Request failed (${res.status})`);
    }
    return data;
}

function openModal(title, htmlContent) {
    document.getElementById("modalTitle").textContent = title;
    document.getElementById("modalBody").innerHTML = htmlContent;
    document.getElementById("detailModal").hidden = false;
}

function closeModal() {
    document.getElementById("detailModal").hidden = true;
}

document.getElementById("modalCloseBtn").addEventListener("click", closeModal);
document.getElementById("detailModal").addEventListener("click", e => {
    if (e.target.id === "detailModal") closeModal();
});

// =====================================
// DASHBOARD
// =====================================

async function loadDashboard() {
    const data = await apiFetch("/api/dashboard");
    document.getElementById("statStudents").textContent = data.total_students;
    document.getElementById("statEnrollments").textContent = `${data.total_enrollments} total enrollments`;
    document.getElementById("statCourses").textContent = data.total_courses;
    document.getElementById("statDepartments").textContent = `${data.total_departments} departments`;
    document.getElementById("statAttendance").textContent = `${data.average_attendance}%`;
    document.getElementById("statPerf").textContent =
        `Avg Score: ${data.academic_overview.average_percentage}% (Pass: ${data.academic_overview.pass_rate}%)`;
    document.getElementById("statFeeCollected").textContent = formatINR(data.total_fee_collection);
    document.getElementById("statFeePending").textContent = `Pending: ${formatINR(data.pending_fee_payments)}`;

    const admEl = document.getElementById("recentAdmissionsList");
    admEl.innerHTML = data.recent_admissions.length
        ? data.recent_admissions.map(s =>
            `<div><strong>${escapeHTML(s.name)}</strong> (${escapeHTML(s.student_code)}) — ${escapeHTML(s.course_name)}</div>`
        ).join("")
        : "No recent admissions.";

    const payEl = document.getElementById("recentPaymentsList");
    payEl.innerHTML = data.recent_payments.length
        ? data.recent_payments.map(p =>
            `<div><strong>${escapeHTML(p.student_name)}</strong> (${escapeHTML(p.student_code)}): ${formatINR(p.amount_paid)} <span class="badge ${p.status.toLowerCase()}">${escapeHTML(p.status)}</span></div>`
        ).join("")
        : "No fee records yet.";

    const distEl = document.getElementById("courseDistributionList");
    distEl.innerHTML = data.course_distribution.length
        ? data.course_distribution.map(c =>
            `<span class="badge pending" style="margin:3px;">${escapeHTML(c.course_code)}: ${c.student_count} student(s)</span>`
        ).join(" ")
        : "No courses yet.";
}

// =====================================
// DEPARTMENTS
// =====================================

async function loadDepartments() {
    allDepartments = await apiFetch("/api/departments");
    renderDepartmentGrid();
    populateDepartmentDropdowns();
}

function populateDepartmentDropdowns() {
    const selects = [
        { id: "stuDepartment", placeholder: "Select department" },
        { id: "stuFilterDept", placeholder: "All Departments" },
        { id: "courseDepartment", placeholder: "Select department" },
        { id: "courseFilterDept", placeholder: "All Departments" },
        { id: "assignDeptSelect", placeholder: "Choose a department" }
    ];
    selects.forEach(({ id, placeholder }) => {
        const el = document.getElementById(id);
        if (!el) return;
        const cur = el.value;
        el.innerHTML = `<option value="">${placeholder}</option>` +
            allDepartments.map(d => `<option value="${d.id}">${escapeHTML(d.name)} (${escapeHTML(d.code)})</option>`).join("");
        if (allDepartments.some(d => String(d.id) === String(cur))) el.value = cur;
    });
}

function renderDepartmentGrid() {
    const grid = document.getElementById("departmentGrid");
    if (!allDepartments.length) {
        grid.innerHTML = `<div style="color:#64748b; padding:20px;">No departments found.</div>`;
        return;
    }
    grid.innerHTML = allDepartments.map(d => `
        <div class="course-card">
            <div style="color:#a78bfa; font-size:11px; font-weight:700; margin-bottom:10px;">${escapeHTML(d.code)}</div>
            <h3>${escapeHTML(d.name)}</h3>
            <p>HOD: ${escapeHTML(d.manager_name || "Unassigned")}</p>
            <p>Courses: <strong>${d.course_count}</strong> | Students: <strong>${d.student_count}</strong></p>
            <p>${escapeHTML(d.description || "No description")}</p>
            <button class="secondary-btn" onclick="viewDepartment(${d.id})">View</button>
            ${IS_ADMIN ? `
                <button class="secondary-btn" onclick="editDepartment(${d.id})">Edit</button>
                <button class="secondary-btn" onclick="deleteDepartment(${d.id})">Delete</button>
            ` : ""}
        </div>
    `).join("");
}

async function viewDepartment(id) {
    try {
        const d = await apiFetch(`/api/departments/${id}`);
        const list = d.courses.length
            ? d.courses.map(c => `<li>${escapeHTML(c.course_name)} (${escapeHTML(c.course_code)}) — ${escapeHTML(c.duration)}</li>`).join("")
            : "<li>No courses assigned yet.</li>";
        openModal(`Department: ${d.name}`, `
            <div class="detail-grid">
                <div class="detail-item"><small>Code</small><strong>${escapeHTML(d.code)}</strong></div>
                <div class="detail-item"><small>HOD</small><strong>${escapeHTML(d.manager_name || "-")}</strong></div>
                <div class="detail-item"><small>Courses</small><strong>${d.course_count}</strong></div>
                <div class="detail-item"><small>Students</small><strong>${d.student_count}</strong></div>
            </div>
            <h4 style="margin-bottom:8px;">Assigned Courses</h4>
            <ul style="padding-left:18px;">${list}</ul>
        `);
    } catch (err) {
        showToast(err.message, "error");
    }
}

function editDepartment(id) {
    const d = allDepartments.find(x => x.id === id);
    if (!d) return;
    document.getElementById("deptEditId").value = d.id;
    document.getElementById("deptName").value = d.name;
    document.getElementById("deptCode").value = d.code;
    document.getElementById("deptManager").value = d.manager_name || "";
    document.getElementById("deptDesc").value = d.description || "";
    document.getElementById("deptSubmitBtn").textContent = "Save Department";
    document.getElementById("cancelDeptEdit").hidden = false;
    document.getElementById("departmentForm").scrollIntoView({ behavior: "smooth", block: "center" });
}

function resetDepartmentForm() {
    const f = document.getElementById("departmentForm");
    if (!f) return;
    f.reset();
    document.getElementById("deptEditId").value = "";
    document.getElementById("deptSubmitBtn").textContent = "+ Add Department";
    document.getElementById("cancelDeptEdit").hidden = true;
}

async function deleteDepartment(id) {
    const d = allDepartments.find(x => x.id === id);
    if (!d || !confirm(`Delete department "${d.name}"?`)) return;
    try {
        const res = await apiFetch(`/api/departments/${id}`, { method: "DELETE" });
        showToast(res.message);
        await refreshAll();
    } catch (err) {
        showToast(err.message, "error");
    }
}

// =====================================
// COURSES & ENROLLMENTS
// =====================================

async function loadCourses() {
    const search = document.getElementById("courseSearch")?.value || "";
    const department_id = document.getElementById("courseFilterDept")?.value || "";
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (department_id) params.set("department_id", department_id);

    const courses = await apiFetch(`/api/courses?${params.toString()}`);
    if (!search && !department_id) {
        allCourses = courses;
        populateCourseDropdowns();
    }
    renderCourseGrid(courses);
}

function populateCourseDropdowns() {
    const selects = [
        { id: "stuCourse", placeholder: "Select course" },
        { id: "stuFilterCourse", placeholder: "All Courses" },
        { id: "enrollCourse", placeholder: "Choose a course" },
        { id: "assignCourseSelect", placeholder: "Choose a course" },
        { id: "attFilterCourse", placeholder: "All Courses" },
        { id: "examCourse", placeholder: "Choose a course" },
        { id: "fsCourse", placeholder: "Choose a course" }
    ];
    selects.forEach(({ id, placeholder }) => {
        const el = document.getElementById(id);
        if (!el) return;
        const cur = el.value;
        el.innerHTML = `<option value="">${placeholder}</option>` +
            allCourses.map(c => `<option value="${c.id}">${escapeHTML(c.course_name)} (${escapeHTML(c.course_code)})</option>`).join("");
        if (allCourses.some(c => String(c.id) === String(cur))) el.value = cur;
    });
}

function renderCourseGrid(courses) {
    const grid = document.getElementById("courseGrid");
    if (!courses.length) {
        grid.innerHTML = `<div style="color:#64748b; padding:20px;">No courses found.</div>`;
        return;
    }
    grid.innerHTML = courses.map(c => `
        <div class="course-card">
            <div style="color:#a78bfa; font-size:11px; font-weight:700; margin-bottom:10px;">${escapeHTML(c.course_code)}</div>
            <h3>${escapeHTML(c.course_name)}</h3>
            <p>Department: ${escapeHTML(c.department_name)}</p>
            <p>Duration: ${escapeHTML(c.duration)} (${c.num_semesters} Semesters)</p>
            <p>Enrolled Students: <strong>${c.enrolled_count}</strong></p>
            <button class="secondary-btn" onclick="viewCourse(${c.id})">View</button>
            ${IS_ADMIN ? `
                <button class="secondary-btn" onclick="editCourse(${c.id})">Edit</button>
                <button class="secondary-btn" onclick="deleteCourse(${c.id})">Delete</button>
            ` : ""}
        </div>
    `).join("");
}

async function viewCourse(id) {
    try {
        const c = await apiFetch(`/api/courses/${id}`);
        const stuList = c.enrolled_students.length
            ? c.enrolled_students.map(s => `<li>${escapeHTML(s.name)} (${escapeHTML(s.student_code)}) — Sem ${s.semester}</li>`).join("")
            : "<li>No students enrolled (or restricted in student view).</li>";
        openModal(`Course: ${c.course_name}`, `
            <div class="detail-grid">
                <div class="detail-item"><small>Course Code</small><strong>${escapeHTML(c.course_code)}</strong></div>
                <div class="detail-item"><small>Department</small><strong>${escapeHTML(c.department_name)}</strong></div>
                <div class="detail-item"><small>Duration</small><strong>${escapeHTML(c.duration)}</strong></div>
                <div class="detail-item"><small>Semesters</small><strong>${c.num_semesters}</strong></div>
                <div class="detail-item" style="grid-column: 1 / -1;"><small>Description</small><strong>${escapeHTML(c.description || "-")}</strong></div>
            </div>
            <h4 style="margin-bottom:8px;">Enrolled Students (${c.enrolled_count})</h4>
            <ul style="padding-left:18px;">${stuList}</ul>
        `);
    } catch (err) {
        showToast(err.message, "error");
    }
}

function editCourse(id) {
    const c = allCourses.find(x => x.id === id);
    if (!c) return;
    document.getElementById("courseEditId").value = c.id;
    document.getElementById("courseCode").value = c.course_code;
    document.getElementById("courseName").value = c.course_name;
    document.getElementById("courseDepartment").value = c.department_id;
    document.getElementById("courseDuration").value = c.duration;
    document.getElementById("courseSemesters").value = c.num_semesters;
    document.getElementById("courseDesc").value = c.description || "";
    document.getElementById("courseSubmitBtn").textContent = "Save Course";
    document.getElementById("cancelCourseEdit").hidden = false;
    document.getElementById("courseForm").scrollIntoView({ behavior: "smooth", block: "center" });
}

function resetCourseForm() {
    const f = document.getElementById("courseForm");
    if (!f) return;
    f.reset();
    document.getElementById("courseEditId").value = "";
    document.getElementById("courseSubmitBtn").textContent = "+ Add Course";
    document.getElementById("cancelCourseEdit").hidden = true;
}

async function deleteCourse(id) {
    const c = allCourses.find(x => x.id === id);
    if (!c || !confirm(`Delete course "${c.course_name}"?`)) return;
    try {
        const res = await apiFetch(`/api/courses/${id}`, { method: "DELETE" });
        showToast(res.message);
        await refreshAll();
    } catch (err) {
        showToast(err.message, "error");
    }
}

// =====================================
// STUDENTS
// =====================================

async function loadStudents() {
    const search = document.getElementById("stuSearch")?.value || "";
    const department_id = document.getElementById("stuFilterDept")?.value || "";
    const course_id = document.getElementById("stuFilterCourse")?.value || "";
    const semester = document.getElementById("stuFilterSem")?.value || "";
    const sort = document.getElementById("stuSort")?.value || "newest";

    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (department_id) params.set("department_id", department_id);
    if (course_id) params.set("course_id", course_id);
    if (semester) params.set("semester", semester);
    if (sort) params.set("sort", sort);

    const students = await apiFetch(`/api/students?${params.toString()}`);
    if (!search && !department_id && !course_id && !semester) {
        allStudents = students;
        populateStudentDropdowns();
    }
    renderStudentTable(students);
}

function populateStudentDropdowns() {
    const selects = [
        { id: "enrollStudent", placeholder: "Choose a student" },
        { id: "attStudent", placeholder: "Choose a student" },
        { id: "resStudent", placeholder: "Choose a student" },
        { id: "fpStudent", placeholder: "Choose a student" }
    ];
    selects.forEach(({ id, placeholder }) => {
        const el = document.getElementById(id);
        if (!el) return;
        const cur = el.value;
        el.innerHTML = `<option value="">${placeholder}</option>` +
            allStudents.map(s => `<option value="${s.id}">${escapeHTML(s.name)} (${escapeHTML(s.student_code)})</option>`).join("");
        if (allStudents.some(s => String(s.id) === String(cur))) el.value = cur;
    });
}

function renderStudentTable(students) {
    const tbody = document.getElementById("studentTable");
    if (!students.length) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:28px; color:#64748b;">No students found.</td></tr>`;
        return;
    }
    tbody.innerHTML = students.map(s => {
        const badge = s.status === "Active" ? "active" : (s.status === "Graduated" ? "pending" : "inactive");
        return `
            <tr>
                <td>
                    <strong>${escapeHTML(s.name)}</strong><br>
                    <small style="color:#64748b;">${escapeHTML(s.email)}</small>
                </td>
                <td>${escapeHTML(s.student_code)}</td>
                <td>${escapeHTML(s.department_name)}</td>
                <td>${escapeHTML(s.course_name)}</td>
                <td>Sem ${s.semester}</td>
                <td><span class="badge ${badge}">${escapeHTML(s.status)}</span></td>
                <td>
                    <button class="secondary-btn" onclick="viewStudent(${s.id})">View</button>
                    ${IS_ADMIN ? `
                        <button class="secondary-btn" onclick="editStudent(${s.id})">Edit</button>
                        <button class="secondary-btn" onclick="deleteStudent(${s.id})">Delete</button>
                    ` : ""}
                </td>
            </tr>
        `;
    }).join("");
}

async function viewStudent(id) {
    try {
        const s = await apiFetch(`/api/students/${id}`);
        const att = s.attendance_summary;
        const resHtml = s.results.length
            ? s.results.map(r => `<li>${escapeHTML(r.exam_name)}: ${r.marks_obtained}/${r.max_marks} (${r.percentage}% — Grade ${escapeHTML(r.grade)}, ${escapeHTML(r.pass_status)})</li>`).join("")
            : "<li>No exam results recorded.</li>";
        openModal(`Student Profile: ${s.name}`, `
            <div class="detail-grid">
                <div class="detail-item"><small>Student ID</small><strong>${escapeHTML(s.student_code)}</strong></div>
                <div class="detail-item"><small>Status</small><strong>${escapeHTML(s.status)}</strong></div>
                <div class="detail-item"><small>Department</small><strong>${escapeHTML(s.department_name)}</strong></div>
                <div class="detail-item"><small>Course</small><strong>${escapeHTML(s.course_name)} (Sem ${s.semester})</strong></div>
                <div class="detail-item"><small>Email</small><strong>${escapeHTML(s.email)}</strong></div>
                <div class="detail-item"><small>Phone</small><strong>${escapeHTML(s.phone)}</strong></div>
                <div class="detail-item"><small>DOB / Gender</small><strong>${escapeHTML(s.dob)} / ${escapeHTML(s.gender)}</strong></div>
                <div class="detail-item"><small>Admission / Year</small><strong>${escapeHTML(s.admission_date)} (${escapeHTML(s.academic_year)})</strong></div>
                <div class="detail-item" style="grid-column: 1 / -1;"><small>Address</small><strong>${escapeHTML(s.address || "-")}</strong></div>
            </div>
            <p style="margin-bottom:10px;"><strong>Attendance:</strong> ${att.present_days}/${att.total_days} days (${att.attendance_percentage}%)</p>
            <h4 style="margin-bottom:6px;">Examination Results</h4>
            <ul style="padding-left:18px;">${resHtml}</ul>
        `);
    } catch (err) {
        showToast(err.message, "error");
    }
}

function editStudent(id) {
    const s = allStudents.find(x => x.id === id);
    if (!s) return;
    document.getElementById("stuEditId").value = s.id;
    document.getElementById("stuCode").value = s.student_code;
    document.getElementById("stuName").value = s.name;
    document.getElementById("stuEmail").value = s.email;
    document.getElementById("stuPhone").value = s.phone;
    document.getElementById("stuDob").value = s.dob;
    document.getElementById("stuGender").value = s.gender;
    document.getElementById("stuDepartment").value = s.department_id;
    document.getElementById("stuCourse").value = s.course_id;
    document.getElementById("stuSemester").value = s.semester;
    document.getElementById("stuAdmissionDate").value = s.admission_date;
    document.getElementById("stuAcademicYear").value = s.academic_year;
    document.getElementById("stuStatus").value = s.status;
    document.getElementById("stuAddress").value = s.address || "";
    document.getElementById("stuSubmitBtn").textContent = "Save Changes";
    document.getElementById("cancelStuEdit").hidden = false;
    document.getElementById("studentForm").scrollIntoView({ behavior: "smooth", block: "center" });
}

function resetStudentForm() {
    const f = document.getElementById("studentForm");
    if (!f) return;
    f.reset();
    document.getElementById("stuEditId").value = "";
    document.getElementById("stuSubmitBtn").textContent = "+ Add Student";
    document.getElementById("cancelStuEdit").hidden = true;
}

async function deleteStudent(id) {
    const s = allStudents.find(x => x.id === id);
    if (!s || !confirm(`Delete student "${s.name}" (${s.student_code})?`)) return;
    try {
        const res = await apiFetch(`/api/students/${id}`, { method: "DELETE" });
        showToast(res.message);
        await refreshAll();
    } catch (err) {
        showToast(err.message, "error");
    }
}

// =====================================
// ATTENDANCE
// =====================================

async function loadAttendance() {
    const course_id = document.getElementById("attFilterCourse")?.value || "";
    const semester = document.getElementById("attFilterSem")?.value || "";
    const date = document.getElementById("attFilterDate")?.value || "";
    const params = new URLSearchParams();
    if (course_id) params.set("course_id", course_id);
    if (semester) params.set("semester", semester);
    if (date) params.set("date", date);

    const data = await apiFetch(`/api/attendance?${params.toString()}`);
    const tbody = document.getElementById("attendanceTable");
    const cols = IS_ADMIN ? 8 : 7;
    tbody.innerHTML = data.records.length
        ? data.records.map(r => `
            <tr>
                <td>${escapeHTML(r.date)}</td>
                <td>${escapeHTML(r.student_code)}</td>
                <td>${escapeHTML(r.student_name)}</td>
                <td>${escapeHTML(r.course_name || "-")}</td>
                <td>Sem ${r.semester}</td>
                <td><span class="badge ${r.status.toLowerCase()}">${escapeHTML(r.status)}</span></td>
                <td>${escapeHTML(r.notes || "-")}</td>
                ${IS_ADMIN ? `<td><button class="secondary-btn" onclick="deleteAttendance(${r.id})">Delete</button></td>` : ""}
            </tr>
        `).join("")
        : `<tr><td colspan="${cols}" style="text-align:center; padding:24px; color:#64748b;">No attendance records found.</td></tr>`;

    const sumBody = document.getElementById("attendanceSummaryTable");
    sumBody.innerHTML = data.summary.length
        ? data.summary.map(s => `
            <tr>
                <td>${escapeHTML(s.student_code)}</td>
                <td>${escapeHTML(s.student_name)}</td>
                <td>${s.total_days}</td>
                <td>${s.present_days}</td>
                <td>${s.absent_days}</td>
                <td>${s.leave_days}</td>
                <td><strong>${s.attendance_percentage}%</strong></td>
            </tr>
        `).join("")
        : `<tr><td colspan="7" style="text-align:center; padding:24px; color:#64748b;">No attendance summary yet.</td></tr>`;
}

async function deleteAttendance(id) {
    if (!confirm("Delete this attendance record?")) return;
    try {
        const res = await apiFetch(`/api/attendance/${id}`, { method: "DELETE" });
        showToast(res.message);
        await Promise.all([loadAttendance(), loadDashboard()]);
    } catch (err) {
        showToast(err.message, "error");
    }
}

// =====================================
// EXAMINATIONS & RESULTS
// =====================================

async function loadExamsAndResults() {
    const [rules, exams, results] = await Promise.all([
        apiFetch("/api/grading-rules"),
        apiFetch("/api/examinations"),
        apiFetch("/api/results")
    ]);
    allExams = exams;

    const rulesText = rules.map(r => `${r.grade} (>=${r.min_percentage}%)`).join(" | ");
    document.getElementById("gradingRulesText").textContent = `Configurable Grading Scale: ${rulesText}`;

    const resExam = document.getElementById("resExam");
    if (resExam) {
        const cur = resExam.value;
        resExam.innerHTML = `<option value="">Choose an exam</option>` +
            exams.map(e => `<option value="${e.id}">${escapeHTML(e.exam_name)} (${escapeHTML(e.exam_code)} - Max ${e.max_marks})</option>`).join("");
        if (exams.some(e => String(e.id) === String(cur))) resExam.value = cur;
    }

    const examCols = IS_ADMIN ? 7 : 6;
    document.getElementById("examTable").innerHTML = exams.length
        ? exams.map(e => `
            <tr>
                <td>${escapeHTML(e.exam_code)}</td>
                <td>${escapeHTML(e.exam_name)}</td>
                <td>${escapeHTML(e.course_name)}</td>
                <td>Sem ${e.semester}</td>
                <td>${escapeHTML(e.exam_date)}</td>
                <td>${e.max_marks} / ${e.pass_marks}</td>
                ${IS_ADMIN ? `<td><button class="secondary-btn" onclick="deleteExam(${e.id})">Delete</button></td>` : ""}
            </tr>
        `).join("")
        : `<tr><td colspan="${examCols}" style="text-align:center; padding:24px; color:#64748b;">No examinations scheduled.</td></tr>`;

    const resCols = IS_ADMIN ? 8 : 7;
    document.getElementById("resultTable").innerHTML = results.length
        ? results.map(r => `
            <tr>
                <td>${escapeHTML(r.exam_name)} (${escapeHTML(r.exam_code)})</td>
                <td>${escapeHTML(r.student_code)}</td>
                <td>${escapeHTML(r.student_name)}</td>
                <td>${r.marks_obtained} / ${r.max_marks}</td>
                <td>${r.percentage}%</td>
                <td><strong>${escapeHTML(r.grade)}</strong></td>
                <td><span class="badge ${r.pass_status === 'Pass' ? 'approved' : 'rejected'}">${escapeHTML(r.pass_status)}</span></td>
                ${IS_ADMIN ? `<td><button class="secondary-btn" onclick="deleteResult(${r.id})">Delete</button></td>` : ""}
            </tr>
        `).join("")
        : `<tr><td colspan="${resCols}" style="text-align:center; padding:24px; color:#64748b;">No results recorded.</td></tr>`;
}

async function deleteExam(id) {
    if (!confirm("Delete this examination and its results?")) return;
    try {
        const res = await apiFetch(`/api/examinations/${id}`, { method: "DELETE" });
        showToast(res.message);
        await Promise.all([loadExamsAndResults(), loadDashboard()]);
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function deleteResult(id) {
    if (!confirm("Delete this result?")) return;
    try {
        const res = await apiFetch(`/api/results/${id}`, { method: "DELETE" });
        showToast(res.message);
        await Promise.all([loadExamsAndResults(), loadDashboard()]);
    } catch (err) {
        showToast(err.message, "error");
    }
}

// =====================================
// FEES MANAGEMENT
// =====================================

async function loadFees() {
    allFeeStructures = await apiFetch("/api/fee-structures");
    const search = document.getElementById("feeSearch")?.value || "";
    const status = document.getElementById("feeFilterStatus")?.value || "";
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (status) params.set("status", status);

    const payments = await apiFetch(`/api/fee-payments?${params.toString()}`);
    const cols = IS_ADMIN ? 8 : 7;
    document.getElementById("feeTable").innerHTML = payments.length
        ? payments.map(p => {
            const badge = p.status === "Paid" ? "paid" : (p.status === "Partial" ? "pending" : "absent");
            return `
                <tr>
                    <td>${escapeHTML(p.student_code)}</td>
                    <td>${escapeHTML(p.student_name)}</td>
                    <td>Sem ${p.semester} (${escapeHTML(p.academic_year)})</td>
                    <td>${formatINR(p.total_due)}</td>
                    <td>${formatINR(p.amount_paid)}</td>
                    <td><strong>${formatINR(p.balance)}</strong></td>
                    <td><span class="badge ${badge}">${escapeHTML(p.status)}</span></td>
                    ${IS_ADMIN ? `
                        <td>
                            ${p.balance > 0 ? `<button class="secondary-btn" onclick="recordInstallment(${p.id}, ${p.balance})">Pay</button>` : ""}
                            <button class="secondary-btn" onclick="deleteFee(${p.id})">Delete</button>
                        </td>
                    ` : ""}
                </tr>
            `;
        }).join("")
        : `<tr><td colspan="${cols}" style="text-align:center; padding:24px; color:#64748b;">No fee records found.</td></tr>`;
}

async function recordInstallment(feeId, maxBalance) {
    const input = prompt(`Enter payment amount (Max ${maxBalance}):`, String(maxBalance));
    if (input === null) return;
    const amount = parseFloat(input);
    if (isNaN(amount) || amount <= 0) {
        showToast("Please enter a valid positive amount.", "error");
        return;
    }
    try {
        const res = await apiFetch(`/api/fee-payments/${feeId}/pay`, {
            method: "PUT",
            body: JSON.stringify({ amount })
        });
        showToast(res.message);
        await Promise.all([loadFees(), loadDashboard()]);
    } catch (err) {
        showToast(err.message, "error");
    }
}

async function deleteFee(id) {
    if (!confirm("Delete this fee record?")) return;
    try {
        const res = await apiFetch(`/api/fee-payments/${id}`, { method: "DELETE" });
        showToast(res.message);
        await Promise.all([loadFees(), loadDashboard()]);
    } catch (err) {
        showToast(err.message, "error");
    }
}

// =====================================
// FORM LISTENERS
// =====================================

document.getElementById("studentForm")?.addEventListener("submit", async e => {
    e.preventDefault();
    const editId = document.getElementById("stuEditId").value;
    const payload = {
        student_code: document.getElementById("stuCode").value.trim(),
        name: document.getElementById("stuName").value.trim(),
        email: document.getElementById("stuEmail").value.trim(),
        phone: document.getElementById("stuPhone").value.trim(),
        dob: document.getElementById("stuDob").value,
        gender: document.getElementById("stuGender").value,
        department_id: document.getElementById("stuDepartment").value,
        course_id: document.getElementById("stuCourse").value,
        semester: document.getElementById("stuSemester").value,
        admission_date: document.getElementById("stuAdmissionDate").value,
        academic_year: document.getElementById("stuAcademicYear").value.trim(),
        status: document.getElementById("stuStatus").value,
        address: document.getElementById("stuAddress").value.trim()
    };
    try {
        const res = editId
            ? await apiFetch(`/api/students/${editId}`, { method: "PUT", body: JSON.stringify(payload) })
            : await apiFetch("/api/students", { method: "POST", body: JSON.stringify(payload) });
        showToast(res.message);
        resetStudentForm();
        await refreshAll();
    } catch (err) {
        showToast(err.message, "error");
    }
});

document.getElementById("cancelStuEdit")?.addEventListener("click", resetStudentForm);

document.getElementById("courseForm")?.addEventListener("submit", async e => {
    e.preventDefault();
    const editId = document.getElementById("courseEditId").value;
    const payload = {
        course_code: document.getElementById("courseCode").value.trim(),
        course_name: document.getElementById("courseName").value.trim(),
        department_id: document.getElementById("courseDepartment").value,
        duration: document.getElementById("courseDuration").value.trim(),
        num_semesters: document.getElementById("courseSemesters").value,
        description: document.getElementById("courseDesc").value.trim()
    };
    try {
        const res = editId
            ? await apiFetch(`/api/courses/${editId}`, { method: "PUT", body: JSON.stringify(payload) })
            : await apiFetch("/api/courses", { method: "POST", body: JSON.stringify(payload) });
        showToast(res.message);
        resetCourseForm();
        await refreshAll();
    } catch (err) {
        showToast(err.message, "error");
    }
});

document.getElementById("cancelCourseEdit")?.addEventListener("click", resetCourseForm);

document.getElementById("enrollmentForm")?.addEventListener("submit", async e => {
    e.preventDefault();
    try {
        const res = await apiFetch("/api/enrollments", {
            method: "POST",
            body: JSON.stringify({
                student_id: document.getElementById("enrollStudent").value,
                course_id: document.getElementById("enrollCourse").value
            })
        });
        showToast(res.message);
        e.target.reset();
        await refreshAll();
    } catch (err) {
        showToast(err.message, "error");
    }
});

document.getElementById("departmentForm")?.addEventListener("submit", async e => {
    e.preventDefault();
    const editId = document.getElementById("deptEditId").value;
    const payload = {
        name: document.getElementById("deptName").value.trim(),
        code: document.getElementById("deptCode").value.trim(),
        manager_name: document.getElementById("deptManager").value.trim(),
        description: document.getElementById("deptDesc").value.trim()
    };
    try {
        const res = editId
            ? await apiFetch(`/api/departments/${editId}`, { method: "PUT", body: JSON.stringify(payload) })
            : await apiFetch("/api/departments", { method: "POST", body: JSON.stringify(payload) });
        showToast(res.message);
        resetDepartmentForm();
        await refreshAll();
    } catch (err) {
        showToast(err.message, "error");
    }
});

document.getElementById("cancelDeptEdit")?.addEventListener("click", resetDepartmentForm);

document.getElementById("assignCourseForm")?.addEventListener("submit", async e => {
    e.preventDefault();
    const course_id = document.getElementById("assignCourseSelect").value;
    const dept_id = document.getElementById("assignDeptSelect").value;
    try {
        const res = await apiFetch(`/api/departments/${dept_id}/assign-course`, {
            method: "POST",
            body: JSON.stringify({ course_id })
        });
        showToast(res.message);
        e.target.reset();
        await refreshAll();
    } catch (err) {
        showToast(err.message, "error");
    }
});

document.getElementById("attendanceForm")?.addEventListener("submit", async e => {
    e.preventDefault();
    try {
        const res = await apiFetch("/api/attendance", {
            method: "POST",
            body: JSON.stringify({
                student_id: document.getElementById("attStudent").value,
                date: document.getElementById("attDate").value,
                status: document.getElementById("attStatus").value,
                notes: document.getElementById("attNotes").value.trim()
            })
        });
        showToast(res.message);
        document.getElementById("attNotes").value = "";
        await Promise.all([loadAttendance(), loadDashboard()]);
    } catch (err) {
        showToast(err.message, "error");
    }
});

document.getElementById("examForm")?.addEventListener("submit", async e => {
    e.preventDefault();
    try {
        const res = await apiFetch("/api/examinations", {
            method: "POST",
            body: JSON.stringify({
                exam_code: document.getElementById("examCode").value.trim(),
                exam_name: document.getElementById("examName").value.trim(),
                course_id: document.getElementById("examCourse").value,
                semester: document.getElementById("examSemester").value,
                exam_date: document.getElementById("examDate").value,
                max_marks: document.getElementById("examMaxMarks").value,
                pass_marks: document.getElementById("examPassMarks").value
            })
        });
        showToast(res.message);
        e.target.reset();
        await loadExamsAndResults();
    } catch (err) {
        showToast(err.message, "error");
    }
});

document.getElementById("resultForm")?.addEventListener("submit", async e => {
    e.preventDefault();
    try {
        const res = await apiFetch("/api/results", {
            method: "POST",
            body: JSON.stringify({
                examination_id: document.getElementById("resExam").value,
                student_id: document.getElementById("resStudent").value,
                marks_obtained: document.getElementById("resMarks").value,
                remarks: document.getElementById("resRemarks").value.trim()
            })
        });
        showToast(`${res.message} (Grade: ${res.grade}, ${res.pass_status})`);
        e.target.reset();
        await Promise.all([loadExamsAndResults(), loadDashboard()]);
    } catch (err) {
        showToast(err.message, "error");
    }
});

document.getElementById("feeStructureForm")?.addEventListener("submit", async e => {
    e.preventDefault();
    try {
        const res = await apiFetch("/api/fee-structures", {
            method: "POST",
            body: JSON.stringify({
                course_id: document.getElementById("fsCourse").value,
                semester: document.getElementById("fsSemester").value,
                academic_year: document.getElementById("fsYear").value.trim(),
                tuition_fee: document.getElementById("fsTuition").value,
                lab_fee: document.getElementById("fsLab").value,
                library_fee: document.getElementById("fsLibrary").value,
                other_fee: 0
            })
        });
        showToast(`${res.message} Total: ${formatINR(res.total_fee)}`);
        await loadFees();
    } catch (err) {
        showToast(err.message, "error");
    }
});

document.getElementById("feePaymentForm")?.addEventListener("submit", async e => {
    e.preventDefault();
    try {
        const res = await apiFetch("/api/fee-payments", {
            method: "POST",
            body: JSON.stringify({
                student_id: document.getElementById("fpStudent").value,
                semester: document.getElementById("fpSemester").value,
                academic_year: document.getElementById("fpYear").value.trim(),
                total_due: document.getElementById("fpTotalDue").value,
                amount_paid: document.getElementById("fpAmountPaid").value,
                payment_method: document.getElementById("fpMethod").value
            })
        });
        showToast(res.message);
        await Promise.all([loadFees(), loadDashboard()]);
    } catch (err) {
        showToast(err.message, "error");
    }
});

// Search & filter listeners
["stuSearch", "stuFilterDept", "stuFilterCourse", "stuFilterSem", "stuSort"].forEach(id => {
    document.getElementById(id)?.addEventListener("input", loadStudents);
    document.getElementById(id)?.addEventListener("change", loadStudents);
});

["courseSearch", "courseFilterDept"].forEach(id => {
    document.getElementById(id)?.addEventListener("input", loadCourses);
    document.getElementById(id)?.addEventListener("change", loadCourses);
});

["attFilterCourse", "attFilterSem", "attFilterDate"].forEach(id => {
    document.getElementById(id)?.addEventListener("change", loadAttendance);
});

document.getElementById("attClearFilters")?.addEventListener("click", () => {
    if (document.getElementById("attFilterCourse")) document.getElementById("attFilterCourse").value = "";
    if (document.getElementById("attFilterSem")) document.getElementById("attFilterSem").value = "";
    document.getElementById("attFilterDate").value = "";
    loadAttendance();
});

["feeSearch", "feeFilterStatus"].forEach(id => {
    document.getElementById(id)?.addEventListener("input", loadFees);
    document.getElementById(id)?.addEventListener("change", loadFees);
});

// Sidebar nav active state
document.querySelectorAll(".nav").forEach(link => {
    link.addEventListener("click", function () {
        document.querySelectorAll(".nav").forEach(n => n.classList.remove("active"));
        this.classList.add("active");
    });
});

// =====================================
// INITIALIZATION
// =====================================

async function refreshAll() {
    try {
        await loadDashboard();
        await loadDepartments();
        await loadCourses();
        await loadStudents();
        await Promise.all([loadAttendance(), loadExamsAndResults(), loadFees()]);
    } catch (err) {
        showToast(err.message, "error");
    }
}

const todayISO = new Date().toISOString().slice(0, 10);
if (document.getElementById("attDate")) document.getElementById("attDate").value = todayISO;
if (document.getElementById("examDate")) document.getElementById("examDate").value = todayISO;
if (document.getElementById("stuAdmissionDate")) document.getElementById("stuAdmissionDate").value = todayISO;

refreshAll();
