from flask import Flask
from app.extensions import db
import os

def create_app():
    flask_app = Flask(__name__)
    flask_app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key-for-dev')

    db_url = os.environ.get("DATABASE_URL", "sqlite:///autotime.db")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    flask_app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(flask_app)

    with flask_app.app_context():
        # Import models so they are registered with SQLAlchemy
        import app.models
        db.create_all()

    # Import routes
    from app.routes import main_bp
    flask_app.register_blueprint(main_bp)

    return flask_app
