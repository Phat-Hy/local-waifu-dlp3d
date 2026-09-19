import asyncio
import websockets
import json

async def test_chat():
    uri = "ws://127.0.0.1:18002/ws/chat"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"text": "tell me funfact about koala"}))
        print("Sent question: 'tell me funfact about koala'\n")
        tokens = []
        audio_packets = 0
        while True:
            msg_raw = await asyncio.wait_for(ws.recv(), timeout=35)
            msg = json.loads(msg_raw)
            m_type = msg.get("type")
            if m_type == "token":
                tokens.append(msg.get("content", ""))
                print(msg.get("content", ""), end="", flush=True)
            elif m_type == "audio_packet":
                audio_packets += 1
                txt = msg.get("text", "")
                emo = msg.get("emotion", "neutral")
                gest = msg.get("gesture", "none")
                audio_len = len(msg.get("audio_base64", ""))
                print(f"\n>>> [Audio Packet #{audio_packets} | Emotion: {emo} | Gesture: {gest} | Audio: {audio_len} b64 chars]: {txt}")
            elif m_type == "done":
                print("\n\n=== Stream Done! Total audio packets:", audio_packets, "===")
                break

if __name__ == "__main__":
    asyncio.run(test_chat())
