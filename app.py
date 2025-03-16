from flask import Flask, jsonify, request
from flask_cors import CORS
from librouteros import connect
from cryptography.fernet import Fernet
from celery import Celery
import sqlite3
import time

app = Flask(__name__)
CORS(app)

# Encryption setup
key = Fernet.generate_key()
cipher = Fernet(key)

# Celery configuration
app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'
celery = Celery(app.name, broker=app.config['CELERY_BROKER_URL'])
celery.conf.update(app.config)

# Database setup
def init_db():
    conn = sqlite3.connect('devices.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS devices
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT,
                  ip TEXT,
                  user TEXT,
                  password BLOB)''')
    conn.commit()
    conn.close()

init_db()

# MikroTik API Helper
class MikroTikAPI:
    def __init__(self, device_id):
        self.device = self.get_device(device_id)
        self.conn = connect(
            host=self.device['ip'],
            username=self.device['user'],
            password=cipher.decrypt(self.device['password']).decode()
        )

    def get_device(self, device_id):
        conn = sqlite3.connect('devices.db')
        c = conn.cursor()
        c.execute("SELECT * FROM devices WHERE id=?", (device_id,))
        device = c.fetchone()
        conn.close()
        return {
            'id': device[0],
            'name': device[1],
            'ip': device[2],
            'user': device[3],
            'password': device[4]
        }

    def get_system_resources(self):
        return self.conn(cmd='/system/resource/print')[0]

    def get_interfaces(self):
        return self.conn(cmd='/interface/print')

# API Endpoints
@app.route('/api/devices', methods=['POST'])
def add_device():
    data = request.json
    encrypted_pw = cipher.encrypt(data['password'].encode())
    
    conn = sqlite3.connect('devices.db')
    c = conn.cursor()
    c.execute("INSERT INTO devices (name, ip, user, password) VALUES (?,?,?,?)",
              (data['name'], data['ip'], data['user'], encrypted_pw))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/devices/<int:device_id>/resources')
def get_resources(device_id):
    api = MikroTikAPI(device_id)
    return jsonify(api.get_system_resources())

# Celery Tasks
@celery.task
def poll_devices():
    conn = sqlite3.connect('devices.db')
    c = conn.cursor()
    c.execute("SELECT * FROM devices")
    devices = c.fetchall()
    
    for device in devices:
        try:
            api = MikroTikAPI(device[0])
            resources = api.get_system_resources()
            # Save to time-series database
            save_metrics(device[0], resources)
        except Exception as e:
            print(f"Error polling device {device[0]}: {str(e)}")

def save_metrics(device_id, data):
    # Implement InfluxDB/Grafana integration here
    pass

if __name__ == '__main__':
    app.run(debug=True)
