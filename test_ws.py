
import asyncio
import websockets
import json

async def test_stt():
    uri = "ws://127.0.0.1:8000/api/ws"
    async with websockets.connect(uri) as websocket:
        # Wait for connection proactive message
        msg = await websocket.recv()
        print("Connected:", msg)
        
        # Send empty audio bytes
        # Or better, send a tiny valid wav or webm file? I don't have one. 
        # I'll just send some dummy bytes
        await websocket.send(b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00")
        
        # Send stream_end
        await websocket.send(json.dumps({"type": "stream_end"}))
        
        # Wait for transcript
        while True:
            resp = await websocket.recv()
            print("Response:", resp)
            try:
                data = json.loads(resp)
                if data.get("type") == "transcript":
                    break
            except:
                pass

asyncio.run(test_stt())

