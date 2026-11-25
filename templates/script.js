
/* =====================================
   CAMPUSFLOW - STUDENT & COURSE SYSTEM
   ===================================== */

const STORAGE_KEY = "campusFlowData";

let students = [];
let courses = [];

// Load saved data
function loadData() {
    try {
        const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));

        if (saved) {
            students = Array.isArray(saved.students) ? saved.students : [];
            courses = Array.isArray(saved.courses) ? saved.courses : [];
        }
    } catch (error) {
        console.error("Error loading data:", error);
        students = [];
        courses = [];
    }

    // Ensure all students have courseIds
    students.forEach(student => {
        if (!Array.isArray(student.courseIds)) {
            student.courseIds = [];
        }
    });
}

// Save data
function saveData() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
        students,
        courses
    }));
}

// Generate unique IDs
function makeId() {
    return Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
}

// Escape HTML to prevent HTML injection
function escapeHTML(value) {
    return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    })[char]);
}

// Get course names for a student
function getStudentCourses(student) {
    return (student.courseIds || [])
        .map(id => courses.find(course => course.id === id))
        .filter(Boolean);
}

// =====================================
// DASHBOARD STATISTICS
// =====================================

function updateDashboard() {
    document.getElementById("totalStudents").textContent = students.length;

    document.getElementById("totalCourses").textContent = courses.length;

    const totalEnrollments = students.reduce((total, student) => {
        return total + (student.courseIds?.length || 0);
    }, 0);

    document.getElementById("totalEnrollments").textContent = totalEnrollments;

    const activeCount = students.filter(student =>
        student.status === "Active"
    ).length;

    document.getElementById("activeStudents").textContent = activeCount;
}

// =====================================
// STUDENT MANAGEMENT
// =====================================

const studentForm = document.getElementById("studentForm");

studentForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const id = document.getElementById("studentId").value;

    const name = document.getElementById("studentName").value.trim();
    const email = document.getElementById("studentEmail").value.trim();
    const rollNumber = document.getElementById("rollNumber").value.trim();
    const department = document.getElementById("studentDepartment").value;
    const year = document.getElementById("studentYear").value;
    const status = document.getElementById("studentStatus").value;

    if (!name || !email || !rollNumber || !department || !year) {
        alert("Please fill in all required fields.");
        return;
    }

    // Duplicate ID check
    const duplicateRoll = students.find(student =>
        student.rollNumber.toLowerCase() === rollNumber.toLowerCase() &&
        student.id !== id
    );

    if (duplicateRoll) {
        alert("Student ID already exists!");
        return;
    }

    // Duplicate email check
    const duplicateEmail = students.find(student =>
        student.email.toLowerCase() === email.toLowerCase() &&
        student.id !== id
    );

    if (duplicateEmail) {
        alert("Email already registered!");
        return;
    }

    if (id) {
        // Update student
        const student = students.find(s => s.id === id);

        if (student) {
            student.name = name;
            student.email = email;
            student.rollNumber = rollNumber;
            student.department = department;
            student.year = year;
            student.status = status;
        }

        alert("Student updated successfully!");
    } else {
        // Add new student
        students.push({
            id: makeId(),
            name,
            email,
            rollNumber,
            department,
            year,
            status,
            courseIds: []
        });

        alert("Student added successfully!");
    }

    saveData();
    renderAll();
    resetStudentForm();
});

// Reset student form
function resetStudentForm() {
    studentForm.reset();

    document.getElementById("studentId").value = "";
    document.getElementById("studentSubmit").textContent = "+ Add Student";
    document.getElementById("cancelEdit").hidden = true;
}

// Edit student
function editStudent(id) {
    const student = students.find(s => s.id === id);

    if (!student) return;

    document.getElementById("studentId").value = student.id;
    document.getElementById("studentName").value = student.name;
    document.getElementById("studentEmail").value = student.email;
    document.getElementById("rollNumber").value = student.rollNumber;
    document.getElementById("studentDepartment").value = student.department;
    document.getElementById("studentYear").value = student.year;
    document.getElementById("studentStatus").value = student.status;

    document.getElementById("studentSubmit").textContent = "Save Changes";
    document.getElementById("cancelEdit").hidden = false;

    document.getElementById("studentForm").scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
}

// Delete student
function deleteStudent(id) {
    const student = students.find(s => s.id === id);

    if (!student) return;

    if (!confirm(`Delete student ${student.name}?`)) return;

    students = students.filter(s => s.id !== id);

    saveData();
    renderAll();
}

// Cancel student edit
document.getElementById("cancelEdit").addEventListener("click", resetStudentForm);

// Student search
document.getElementById("studentSearch").addEventListener("input", function () {
    renderStudents(this.value);
});

// Render student table
function renderStudents(search = "") {
    const table = document.getElementById("studentTable");

    const query = search.trim().toLowerCase();

    const filteredStudents = students.filter(student => {
        return (
            student.name.toLowerCase().includes(query) ||
            student.email.toLowerCase().includes(query) ||
            student.rollNumber.toLowerCase().includes(query) ||
            student.department.toLowerCase().includes(query)
        );
    });

    if (filteredStudents.length === 0) {
        table.innerHTML = `
            <tr>
                <td colspan="7" style="text-align:center; padding:30px; color:#64748b;">
                    No students found.
                </td>
            </tr>
        `;
        return;
    }

    table.innerHTML = filteredStudents.map(student => {
        const studentCourses = getStudentCourses(student);

        return `
            <tr>
                <td>
                    <strong>${escapeHTML(student.name)}</strong><br>
                    <small style="color:#64748b">${escapeHTML(student.email)}</small>
                </td>

                <td>${escapeHTML(student.rollNumber)}</td>

                <td>${escapeHTML(student.department)}</td>

                <td>${escapeHTML(student.year)}</td>

                <td>
                    <span class="badge ${student.status === "Active" ? "active" : "inactive"}">
                        ${escapeHTML(student.status)}
                    </span>
                </td>

                <td>${studentCourses.length}</td>

                <td>
                    <button class="secondary-btn" onclick="editStudent('${student.id}')">Edit</button>
                    <button class="secondary-btn" onclick="deleteStudent('${student.id}')">Delete</button>
                </td>
            </tr>
        `;
    }).join("");
}

// =====================================
// COURSE MANAGEMENT
// =====================================

const courseForm = document.getElementById("courseForm");

courseForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const id = document.getElementById("courseId").value;

    const name = document.getElementById("courseName").value.trim();
    const code = document.getElementById("courseCode").value.trim().toUpperCase();
    const instructor = document.getElementById("courseInstructor").value.trim();
    const credits = Number(document.getElementById("courseCredits").value);

    if (!name || !code || !instructor || credits < 1) {
        alert("Please enter valid course details.");
        return;
    }

    // Duplicate course code check
    const duplicateCode = courses.find(course =>
        course.code.toLowerCase() === code.toLowerCase() &&
        course.id !== id
    );

    if (duplicateCode) {
        alert("Course code already exists!");
        return;
    }

    if (id) {
        // Update course
        const course = courses.find(c => c.id === id);

        if (course) {
            course.name = name;
            course.code = code;
            course.instructor = instructor;
            course.credits = credits;
        }

        alert("Course updated successfully!");
    } else {
        // Add course
        courses.push({
            id: makeId(),
            name,
            code,
            instructor,
            credits
        });

        alert("Course added successfully!");
    }

    saveData();
    renderAll();
    resetCourseForm();
});

// Reset course form
function resetCourseForm() {
    courseForm.reset();

    document.getElementById("courseId").value = "";
    document.getElementById("courseCredits").value = 3;
    document.getElementById("courseSubmit").textContent = "+ Add Course";
    document.getElementById("cancelCourseEdit").hidden = true;
}

// Edit course
function editCourse(id) {
    const course = courses.find(c => c.id === id);

    if (!course) return;

    document.getElementById("courseId").value = course.id;
    document.getElementById("courseName").value = course.name;
    document.getElementById("courseCode").value = course.code;
    document.getElementById("courseInstructor").value = course.instructor;
    document.getElementById("courseCredits").value = course.credits;

    document.getElementById("courseSubmit").textContent = "Save Changes";
    document.getElementById("cancelCourseEdit").hidden = false;

    courseForm.scrollIntoView({
        behavior: "smooth",
        block: "center"
    });
}

// Delete course
function deleteCourse(id) {
    const course = courses.find(c => c.id === id);

    if (!course) return;

    if (!confirm(`Delete course "${course.name}"?`)) return;

    courses = courses.filter(c => c.id !== id);

    // Remove this course from all student enrollments
    students.forEach(student => {
        student.courseIds = (student.courseIds || []).filter(courseId => courseId !== id);
    });

    saveData();
    renderAll();
}

// Cancel course edit
document.getElementById("cancelCourseEdit").addEventListener("click", resetCourseForm);

// Render courses
function renderCourses() {
    const grid = document.getElementById("courseGrid");

    if (courses.length === 0) {
        grid.innerHTML = `
            <div style="color:#64748b; padding:20px;">
                No courses added yet. Create your first course above.
            </div>
        `;
        return;
    }

    grid.innerHTML = courses.map(course => `
        <div class="course-card">
            <div style="color:#a78bfa; font-size:11px; font-weight:700; margin-bottom:10px;">
                ${escapeHTML(course.code)}
            </div>

            <h3>${escapeHTML(course.name)}</h3>

            <p>Instructor: ${escapeHTML(course.instructor)}</p>

            <p>Credits: ${escapeHTML(course.credits)}</p>

            <p>Enrolled Students: ${students.filter(s =>
                (s.courseIds || []).includes(course.id)
            ).length}</p>

            <button class="secondary-btn" onclick="editCourse('${course.id}')">
                Edit
            </button>

            <button class="secondary-btn" onclick="deleteCourse('${course.id}')">
                Delete
            </button>
        </div>
    `).join("");
}

// =====================================
// ENROLLMENT MANAGEMENT
// =====================================

const enrollmentForm = document.getElementById("enrollmentForm");

enrollmentForm.addEventListener("submit", function (e) {
    e.preventDefault();

    const studentId = document.getElementById("enrollStudent").value;
    const courseId = document.getElementById("enrollCourse").value;

    const student = students.find(s => s.id === studentId);
    const course = courses.find(c => c.id === courseId);

    if (!student || !course) {
        alert("Please select a valid student and course.");
        return;
    }

    if (student.courseIds.includes(courseId)) {
        alert("This student is already enrolled in this course!");
        return;
    }

    student.courseIds.push(courseId);

    saveData();
    renderAll();

    enrollmentForm.reset();

    alert(`${student.name} enrolled in ${course.name} successfully!`);
});

// Remove enrollment
function removeEnrollment(studentId, courseId) {
    const student = students.find(s => s.id === studentId);

    if (!student) return;

    const course = courses.find(c => c.id === courseId);

    if (!confirm(`Remove ${student.name} from ${course?.name || "this course"}?`)) {
        return;
    }

    student.courseIds = student.courseIds.filter(id => id !== courseId);

    saveData();
    renderAll();
}

// Render dropdown options
function renderEnrollmentOptions() {
    const studentSelect = document.getElementById("enrollStudent");
    const courseSelect = document.getElementById("enrollCourse");

    const selectedStudent = studentSelect.value;
    const selectedCourse = courseSelect.value;

    studentSelect.innerHTML = `
        <option value="">Choose a student</option>
        ${students.map(student => `
            <option value="${student.id}">
                ${escapeHTML(student.name)} (${escapeHTML(student.rollNumber)})
            </option>
        `).join("")}
    `;

    courseSelect.innerHTML = `
        <option value="">Choose a course</option>
        ${courses.map(course => `
            <option value="${course.id}">
                ${escapeHTML(course.name)} (${escapeHTML(course.code)})
            </option>
        `).join("")}
    `;

    // Preserve selections where possible
    if (students.some(s => s.id === selectedStudent)) {
        studentSelect.value = selectedStudent;
    }

    if (courses.some(c => c.id === selectedCourse)) {
        courseSelect.value = selectedCourse;
    }
}

// Render enrollment table
function renderEnrollments() {
    const table = document.getElementById("enrollmentTable");

    const enrolledStudents = students.filter(student =>
        (student.courseIds || []).length > 0
    );

    if (enrolledStudents.length === 0) {
        table.innerHTML = `
            <tr>
                <td colspan="3" style="text-align:center; padding:30px; color:#64748b;">
                    No enrollments yet.
                </td>
            </tr>
        `;
        return;
    }

    table.innerHTML = enrolledStudents.map(student => {
        const studentCourses = getStudentCourses(student);

        return `
            <tr>
                <td>
                    <strong>${escapeHTML(student.name)}</strong>
                </td>

                <td>${escapeHTML(student.rollNumber)}</td>

                <td>
                    ${studentCourses.map(course => `
                        <div style="display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:10px;">
                            <span>
                                ${escapeHTML(course.name)}
                                <small style="color:#64748b;">(${escapeHTML(course.code)})</small>
                            </span>

                            <button class="secondary-btn"
                                onclick="removeEnrollment('${student.id}','${course.id}')">
                                Remove
                            </button>
                        </div>
                    `).join("")}
                </td>
            </tr>
        `;
    }).join("");
}

// =====================================
// RENDER EVERYTHING
// =====================================

function renderAll() {
    updateDashboard();
    renderStudents(document.getElementById("studentSearch").value);
    renderCourses();
    renderEnrollmentOptions();
    renderEnrollments();
}

// =====================================
// NAVIGATION ACTIVE STATE
// =====================================

document.querySelectorAll(".nav").forEach(link => {
    link.addEventListener("click", function () {
        document.querySelectorAll(".nav").forEach(nav => {
            nav.classList.remove("active");
        });

        this.classList.add("active");
    });
});

// =====================================
// INITIALIZATION
// =====================================

loadData();
renderAll();
