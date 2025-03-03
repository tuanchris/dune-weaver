import socketio

# Create a Socket.IO client instance
sio = socketio.Client()

# Event handler for a successful connection on the /ws/status namespace
@sio.event(namespace='/ws/status')
def connect():
    print("Connected to /ws/status namespace")

# Event handler for connection errors on the /ws/status namespace
@sio.event(namespace='/ws/status')
def connect_error(data):
    print("Connection failed:", data)

# Event handler for disconnection from the /ws/status namespace
@sio.event(namespace='/ws/status')
def disconnect():
    print("Disconnected from /ws/status namespace")

# Listen for 'status_update' events in the /ws/status namespace
@sio.on('status_update', namespace='/ws/status')
def on_status_update(data):
    print("Received status update:", data)

if __name__ == "__main__":
    # Replace with your server address if different
    server_url = "http://192.168.2.131:8080"
    try:
        sio.connect(server_url, namespaces=['/ws/status'])
        print("Waiting for status updates...")
        # Keep the client running to listen for events
        sio.wait()
    except Exception as e:
        print("An error occurred:", e)