import websocket
import base64

def on_message(ws, message):
    print(message)

def on_error(ws, error):
    print(error)

def on_close(ws, close_status_code, close_msg):
    print("### closed ###")

def on_open(ws):
    print("Opened connection")

if __name__ == "__main__":
    websocket.enableTrace(True)

    # --- Basic Auth Credentials ---
    # Replace with your actual go2rtc username and password
    USERNAME = "admin"
    PASSWORD = "pass"

    # Encode credentials to Base64
    credentials = f"{USERNAME}:{PASSWORD}".encode("utf-8")
    encoded_credentials = base64.b64encode(credentials).decode("utf-8")

    # Construct the Authorization header
    auth_header = f"Basic {encoded_credentials}"
    print(auth_header)

    ws = websocket.WebSocketApp("ws://10.5.47.10:1984/api/ws?src=tapo_c100",
                              on_open=on_open,
                              on_message=on_message,
                              on_error=on_error,
                              on_close=on_close,
                              header={'Authorization': auth_header})

    ws.run_forever(reconnect=5)