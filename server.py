import json
import os
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
import asyncio
from dotenv import load_dotenv
from retrieval_pipeline import KoanAssistant

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_sessions = {}

class AnswerRequest(BaseModel):
    text: str

@app.get("/")
async def root():
    return {"status": "Koan server is running", "version": "0.1.0"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/sidebar.html")
async def get_sidebar():
    with open("sidebar.html") as f:
        return Response(content=f.read(), media_type="text/html")

@app.get("/voice.html")
async def get_voice_app():
    with open("voice_app.html") as f:
        return Response(content=f.read(), media_type="text/html")

@app.post("/api/answer")
async def get_answer(request: AnswerRequest):
    assistant = KoanAssistant()
    result = assistant.process_transcript_chunk(text=request.text, speaker="user")
    return result if result else {"error": "No answer found", "confidence": 0}

@app.websocket("/ws/zoom/{meeting_id}")
async def websocket_endpoint(websocket: WebSocket, meeting_id: str):
    await websocket.accept()
    assistant = KoanAssistant()
    active_sessions[meeting_id] = {"assistant": assistant, "websocket": websocket}
    print(f"✓ Meeting started: {meeting_id}")
    try:
        while True:
            data = await websocket.receive_text()
            caption_event = json.loads(data)
            if caption_event.get("action") == "caption":
                result = assistant.process_transcript_chunk(
                    text=caption_event["object"]["caption"],
                    speaker=caption_event["object"]["speakerId"]
                )
                if result:
                    await websocket.send_text(json.dumps({
                        "action": "answer",
                        "meeting_id": meeting_id,
                        "payload": result
                    }))
            elif caption_event.get("action") == "stop":
                break
    finally:
        if meeting_id in active_sessions:
            del active_sessions[meeting_id]
        await websocket.close()

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 3000))
    uvicorn.run(app, host="0.0.0.0", port=port)
