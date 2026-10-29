"""GreenLeaf Grocers - inventory & sales management (Flask + SQLite)."""
from flask import Flask, render_template

import database
import models
import routes
from config import Config


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    app.config["MAX_CONTENT_LENGTH"] = app.config["MAX_UPLOAD_BYTES"] + 1024

    database.init_app(app)
    app.register_blueprint(routes.bp)

    with app.app_context():
        database.init_db()
        models.ensure_default_users()

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("error.html", code=404, message="That page or record does not exist."), 404

    @app.errorhandler(413)
    def too_big(_e):
        return render_template("error.html", code=413, message="The uploaded file is too large."), 413

    @app.errorhandler(500)
    def server_error(_e):
        return render_template("error.html", code=500, message="Something went wrong. Please try again."), 500

    return app


if __name__ == "__main__":
    import os
    # Port 5001 avoids the macOS "AirPlay" clash on 5000. Override with: set PORT=8000
    create_app().run(host="127.0.0.1", port=int(os.environ.get("PORT", 5001)), debug=True)
