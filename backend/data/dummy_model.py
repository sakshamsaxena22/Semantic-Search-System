from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/predict', methods=['POST'])
def predict():
    data = request.json
    temperature = data.get('temperature', 30)
    humidity = data.get('humidity', 50)
    soil_moisture = data.get('soil_moisture', 40)

    # Dummy prediction logic
    predicted_moisture = round((temperature + humidity + soil_moisture) / 3 - 5)

    # Solenoid control logic
    solenoid = "ON" if soil_moisture < predicted_moisture else "OFF"

    return jsonify({
        "predicted_moisture": predicted_moisture,
        "solenoid": solenoid
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
