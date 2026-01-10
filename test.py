import websocket
import ssl
import json
import base64
import time
import random
import string

TV_IP = "10.10.97.122"


def get_random_string(length=8):
    letters = string.ascii_letters + string.digits
    return "".join(random.choice(letters) for i in range(length))


def force_pair():
    # 1. Generate a random identity to bypass blacklists
    rand_name = f"Controller_{get_random_string(4)}"
    name_b64 = base64.b64encode(rand_name.encode()).decode()

    print("=" * 60)
    print(f"Attempting Pair as NEW DEVICE: {rand_name}")
    print("=" * 60)

    # 2. Build URI
    uri = f"wss://{TV_IP}:8002/api/v2/channels/samsung.remote.control?name={name_b64}"

    try:
        # 3. Aggressive SSL Context
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        print(f"Connecting to {TV_IP}:8002...")

        ws = websocket.create_connection(
            uri, timeout=30, sslopt={"context": ssl_context}
        )

        print("\n⚠️  LOOK AT YOUR TV NOW! ⚠️")
        print("Waiting for prompt...")

        while True:
            result = ws.recv()
            data = json.loads(result)
            event = data.get("event")

            if event == "ms.channel.connect":
                token = data.get("data", {}).get("token")
                print(f"\n🎉 SUCCESS! Token: {token}")
                ws.close()
                return token

            elif event == "ms.channel.timeOut":
                print("\n❌ TV Rejected Connection (Timeout)")
                print("Did you do the Cold Boot (Unplug from wall)?")
                break

            elif event == "ms.channel.unauthorized":
                print("\n❌ Unauthorized - TV blocked this request")
                break

    except Exception as e:
        print(f"\n❌ Connection Error: {e}")


if __name__ == "__main__":
    force_pair()
