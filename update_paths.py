import sys
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = {
    "'auth.html'": "'auth/auth.html'",
    "'register_institute.html'": "'auth/register_institute.html'",
    "'register_student.html'": "'auth/register_student.html'",
    "'admin_dash.html'": "'admin/admin_dash.html'",
    "'manage_master.html'": "'admin/manage_master.html'",
    "'edit_master.html'": "'admin/edit_master.html'",
    "'college_settings.html'": "'admin/college_settings.html'",
    "'teacher_dash.html'": "'teacher/teacher_dash.html'",
    "'activate_teacher.html'": "'teacher/activate_teacher.html'",
    "'verify_teacher_otp.html'": "'teacher/verify_teacher_otp.html'",
    "'student_dash.html'": "'student/student_dash.html'",
    "'student_portal.html'": "'student/student_portal.html'",
    "'view_timetable.html'": "'shared/view_timetable.html'"
}

for k, v in replacements.items():
    content = content.replace(k, v)

with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("done")
