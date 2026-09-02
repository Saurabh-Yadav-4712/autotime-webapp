
from utils.timetable_adapter import engine_generate_timetable

def test_engine_empty_db(app):
    # Test that engine returns successfully (even if no timetable is generated) and does not crash
    with app.app_context():
        success, message = engine_generate_timetable('TEST01')
        assert success == True
