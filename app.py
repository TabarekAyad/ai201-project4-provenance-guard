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


@app.route("/appeal", methods=["POST"])
def appeal():
    data = request.get_json()
    content_id = data.get("content_id")
    reasoning = data.get("creator_reasoning")

    # Update the content's status and log the appeal (see section 6).
    return jsonify({
        "content_id": content_id,
        "status": "under_review",
        "message": "Your appeal was received and is under review.",
    })

if __name__ == "__main__":
    app.run(port=5000, debug=True)