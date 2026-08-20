import pytest
from app import create_app
from models import db, Institute
from werkzeug.security import generate_password_hash

@pytest.fixture
def app():
    app = create_app(test_config={
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False
    })

    with app.app_context():
        db.create_all()
        # Seed basic institute for tests
        inst = Institute(
            name='Test Inst', 
            institute_code='TEST01', 
            admin_username='admin', 
            admin_email='admin@test.com', 
            admin_password=generate_password_hash('password123')
        )
        db.session.add(inst)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()
