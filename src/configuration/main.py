import json
from flask import Flask, jsonify

app = Flask(__name__)

CONFIG_FILE = 'config.json'

def read_config():
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

@app.route("/config/thresholds", methods=["GET"])
def get_thresholds():
    data = read_config()
    return jsonify(data["thresholds"])

@app.route("/config/actuators", methods=["GET"])
def get_actuators():
    data = read_config()
    return jsonify(data["actuators"])

@app.route("/config/all", methods=["GET"])
def get_all():
    return jsonify(read_config())

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
