from flask import Flask, jsonify
from src.db import get_team_secret


def create_app():
    app = Flask(__name__)

    @app.route("/secret", methods=["GET"])
    def secret():
        secret_value = get_team_secret()
        return jsonify({"secret": secret_value}), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
