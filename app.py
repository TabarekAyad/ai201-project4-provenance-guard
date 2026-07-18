import uuid
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return "Provenance Guard is running."

@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json()
    text = data.get("text")
    creator_id = data.get("creator_id")

    # Placeholder response — wire in your detection signal next.
    return jsonify({
        "content_id": str(uuid.uuid4()),
        "attribution": "uncertain",
        "confidence": 0.5,
        "label": "We're not sure who wrote this.",
    })


if __name__ == "__main__":
    app.run(port=5000, debug=True)