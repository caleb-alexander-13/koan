import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import time
import hmac
import hashlib
from retrieval_pipeline import KoanAssistant

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

assistant = KoanAssistant()
@app.get("/")
async def root():
    with open("landing.html") as f:
        return Response(content=f.read(), media_type="text/html")

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/demo")
async def get_demo():
    with open("voice_app_demo.html") as f:
        return Response(content=f.read(), media_type="text/html")

@app.post("/api/answer")
async def get_answer(request: dict):
    text = request.get("text", "")
    if not text:
        return JSONResponse({"error": "No text provided"}, status_code=400)
    
    result = assistant.generate_answer(text)
    return result

import hmac
import hashlib
import json

ZOOM_WEBHOOK_SECRET = os.getenv("ZOOM_WEBHOOK_SECRET", "hnEpcWPYTmOR5wg9R-YtKw")

def verify_zoom_webhook(request_body: str, auth_header: str) -> bool:
    """Verify Zoom webhook signature"""
    if not auth_header:
        return False
    message = f"v0:{int(time.time())}:{request_body}"
    hash_obj = hmac.new(
        ZOOM_WEBHOOK_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    )
    expected_signature = f"v0={hash_obj.hexdigest()}"
    return hmac.compare_digest(auth_header, expected_signature)

@app.post("/zoom/webhook")
async def zoom_webhook(request: Request):
    """Handle Zoom webhook events"""
    body = await request.body()
    
    # Handle Zoom challenge
    try:
        data = json.loads(body)
        if data.get("event") == "app_deauthorized":
            return {"status": "ok"}
        
        # Zoom challenge-response validation
        if "challenge" in data:
            return {
                "challengeToken": data["challenge"]
            }
        
        # Handle caption events
        if data.get("event") == "meeting.transcript_caption_created":
            caption = data.get("payload", {}).get("object", {}).get("caption", "")
            meeting_id = data.get("payload", {}).get("object", {}).get("meeting_id", "")
            
            if caption:
                print(f"Caption received: {caption}")
                # Process caption through retrieval pipeline
                # koan.generate_answer(caption)
        
        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error"}

ZOOM_WEBHOOK_SECRET = os.getenv("ZOOM_WEBHOOK_SECRET", "hnEpcWPYTmOR5wg9R-YtKw")

@app.post("/zoom/webhook")
async def zoom_webhook(request: Request):
    """Handle Zoom webhook events"""
    body = await request.body()
    
    try:
        data = json.loads(body)
        
        # Zoom challenge-response validation
        if "challenge" in data:
            return {
                "challengeToken": data["challenge"]
            }
        
        # Handle caption events
        if data.get("event") == "meeting.transcript_caption_created":
            caption = data.get("payload", {}).get("object", {}).get("caption", "")
            if caption:
                print(f"Caption received: {caption}")
                # Will process through retrieval pipeline next
        
        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error"}


ZOOM_API_BASE = "https://zoom.us/oauth/token"
ZOOM_API_URL = "https://api.zoom.us/v2"

def get_zoom_access_token():
    """Get Zoom Server-to-Server OAuth token"""
    try:
        auth_str = f"{os.getenv('ZOOM_CLIENT_ID')}:{os.getenv('ZOOM_CLIENT_SECRET')}"
        import base64
        auth_b64 = base64.b64encode(auth_str.encode()).decode()
        
        response = httpx.post(
            ZOOM_API_BASE,
            headers={"Authorization": f"Basic {auth_b64}"},
            data={"grant_type": "account_credentials", "account_id": os.getenv("ZOOM_ACCOUNT_ID")}
        )
        data = response.json()
        return data.get("access_token")
    except Exception as e:
        print(f"Failed to get Zoom token: {e}")
        return None

@app.get("/zoom/captions/{meeting_id}")
async def get_meeting_captions(meeting_id: str):
    """Get captions from an active Zoom meeting"""
    token = get_zoom_access_token()
    if not token:
        return {"error": "Failed to authenticate with Zoom"}
    
    try:
        # Get meeting live transcript
        response = httpx.get(
            f"{ZOOM_API_URL}/meetings/{meeting_id}/live_meeting_details",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code == 200:
            meeting_data = response.json()
            return {"meeting_id": meeting_id, "data": meeting_data}
        else:
            return {"error": "Meeting not found or not live"}
    except Exception as e:
        print(f"Caption fetch error: {e}")
        return {"error": str(e)}

@app.get("/zoom_sidebar.html")
async def get_sidebar():
    with open("sidebar.html") as f:
        return Response(content=f.read(), media_type="text/html")

from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self' 'unsafe-inline' https://*.zoom.us"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

app.add_middleware(SecurityHeadersMiddleware)

@app.get("/oauth/callback")
async def oauth_callback(code: str = None, state: str = None):
    return {"status": "ok", "message": "Koan authorized"}

@app.get("/zoom/oauth")
async def zoom_oauth(code: str = None, state: str = None):
    return {"status": "ok", "message": "Koan authorized"}

from fastapi import WebSocket
import asyncio

@app.websocket("/ws/zoom/{session_id}")
async def zoom_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            await websocket.send_text(data)
    except Exception as e:
        print(f"WebSocket error: {e}")

@app.websocket("/ws/koan/{session_id}")
async def koan_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            text = data.get("text", "")
            if text:
                is_question, question = assistant.detect_question_from_text(text)
                if is_question and question:
                    answer = assistant.generate_answer(question)
                    await websocket.send_text(json.dumps({
                        "action": "answer",
                        "payload": {
                            "question": question,
                            "answer": answer
                        }
                    }))
    except Exception as e:
        print(f"Koan WebSocket error: {e}")

@app.websocket("/ws/koan/{session_id}")
async def koan_websocket(websocket: WebSocket, session_id: str):
    await websocket.accept()
    buffer = []
    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            text = data.get("text", "")
            if text:
                buffer.append(text)
                combined = " ".join(buffer[-5:])
                if "?" in combined or any(w in combined.lower() for w in ["what", "when", "how", "where", "who", "does", "can", "is", "are"]):
                    answer = assistant.generate_answer(combined)
                    buffer = []
                    await websocket.send_text(json.dumps({
                        "action": "answer",
                        "payload": {
                            "question": combined,
                            "answer": answer
                        }
                    }))
    except Exception as e:
        print(f"Koan WebSocket error: {e}")
