from app import create_app
from models import db, Subject, Settings
import math
app = create_app()

with app.app_context():
    subjects = Subject.query.all()
    updated = 0
    for s in subjects:
        weeks_setting = Settings.query.filter_by(institute_code=s.institute_code, key='weeks_per_semester').first()
        weeks = int(weeks_setting.value) if weeks_setting else 15
        
        correct_hrs = math.ceil(s.total_course_hours / weeks)
        if s.required_hours != correct_hrs:
            s.required_hours = correct_hrs
            updated += 1
            
    db.session.commit()
    print(f"Updated {updated} subjects.")
