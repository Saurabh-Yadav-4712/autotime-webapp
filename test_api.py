from app import create_app
from models import db, Institute, Teacher, Subject, Timetable
app = create_app()
app.config['TESTING'] = True

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['institute_code'] = 'TEST'
        sess['admin_id'] = 1
        
    response = client.get('/api/get_slot_data?day=Monday&start_time=10:10&class_id=FYCS')
    print(response.status_code)
    print(response.get_data(as_text=True))
