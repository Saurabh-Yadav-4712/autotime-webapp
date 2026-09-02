import os
from flask import Flask
from models import db
from routes.blueprint import main_bp

import routes.auth
import routes.admin
import routes.student
import routes.teacher

def create_app(test_config=None):
    # Configure Flask to find templates and static files in the root directory
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
                
    app.secret_key = os.environ.get('SECRET_KEY', 'default-secret-key-for-dev')

    if test_config is None:
        db_url = os.environ.get("DATABASE_URL", "sqlite:///autotime.db")
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    else:
        app.config.update(test_config)

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    with app.app_context():
        import models
        db.create_all()
        


    # Register all routes via the shared blueprint
    app.register_blueprint(main_bp)

    return app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
