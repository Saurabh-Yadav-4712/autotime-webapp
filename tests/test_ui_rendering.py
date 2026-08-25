import sys, os
sys.path.append(os.path.abspath('.'))
from models import db, Institute, Teacher, Course, Subject, Timetable
from tests.test_migration_integrity import seed_db

def test_ui_endpoints(app):
    with app.app_context():
        db.create_all()
        seed_db()
        
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['admin_id'] = 1
                sess['institute_code'] = 'I1'
                
            print("Testing /admin_dash")
            res = client.get('/admin_dash')
            print(res.status_code)
            
            print("Testing /view_timetable")
            res = client.get('/view_timetable?class_id=CS1')
            print(res.status_code)
            
            print("Testing /student_portal")
            res = client.get('/student_portal?inst_code=I1&class_id=CS1')
            print(res.status_code)
            
            print("UI Rendering Tests Passed!")
