from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
import json
import os
import time
import hmac
import hashlib
import base64
import requests
import uuid
from retrieval_pipeline import KoanAssistant

app = FastAPI()

# In-memory store for latest answer
latest_answer = {
    "id": str(uuid.uuid4()),
    "caption": "",
    "answer": {"answer": ""},
    "timestamp": 0
}

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'self' https://appssdk.zoom.us; script-src 'self' 'unsafe-inline' https://appssdk.zoom.us; style-src 'self' 'unsafe-inline'"
        response.headers["Referrer-Policy"] = "no-referrer-when-downgrade"
        return response

app.add_middleware(SecurityHeadersMiddleware)
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
    return {"status": "Koan server is running", "version": "0.1.0"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/demo")
async def get_demo():
    with open("voice_app_demo.html") as f:
        return Response(content=f.read(), media_type="text/html")

@app.get("/zoom/sidebar")
async def get_zoom_sidebar():
    with open("zoom_sidebar.html") as f:
        return Response(content=f.read(), media_type="text/html")

@app.post("/api/answer")
async def get_answer(request: dict):
    result = assistant.generate_answer(request.get("text", ""))
    return result

ZOOM_WEBHOOK_SECRET = os.getenv("ZOOM_WEBHOOK_SECRET", "hnEpcWPYTmOR5wg9R-YtKw")

@app.post("/zoom/webhook")
async def zoom_webhook(request: Request):
    """Handle Zoom webhook events"""
    body = await request.body()
    
    try:
        data = json.loads(body)
        
        if "challenge" in data:
            return {
                "challengeToken": data["challenge"]
            }
        
        if data.get("event") == "meeting.transcript_caption_created":
            caption = data.get("payload", {}).get("object", {}).get("caption", "")
            if caption:
                print(f"Caption received: {caption}")
        
        return {"status": "ok"}
    except Exception as e:
        print(f"Webhook error: {e}")
        return {"status": "error"}

@app.get("/zoom/oauth")
async def zoom_oauth(code: str = None, state: str = None):
    """Handle Zoom OAuth callback"""
    if not code:
        return {"error": "No authorization code"}
    
    auth_str = f"{os.getenv('ZOOM_CLIENT_ID')}:{os.getenv('ZOOM_CLIENT_SECRET')}"
    auth_b64 = base64.b64encode(auth_str.encode()).decode()
    
    try:
        token_response = requests.post(
            "https://zoom.us/oauth/token",
            headers={"Authorization": f"Basic {auth_b64}"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "https://koan-0tws.onrender.com/zoom/oauth"
            }
        )
        print(f"Zoom token response: {token_response.status_code} - {token_response.text}")
        token_data = token_response.json()
        access_token = token_data.get("access_token")
        
        if not access_token:
            print(f"No access token in response: {token_data}")
            return {"error": "Failed to get access token", "details": token_data}
        
        return {
            "status": "authorized",
            "access_token": access_token,
            "expires_in": token_data.get("expires_in")
        }
    except Exception as e:
        print(f"OAuth error: {e}")
        return {"error": str(e)}

@app.get("/zoom/captions/{meeting_id}")
async def fetch_zoom_captions(meeting_id: str, access_token: str):
    """Fetch live captions from a Zoom meeting"""
    try:
        response = requests.get(
            f"https://api.zoom.us/v2/meetings/{meeting_id}/recordings",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if response.status_code == 200:
            recording = response.json()
            return {"meeting_id": meeting_id, "recording": recording}
        else:
            return {"error": "Meeting not found or captions not available"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/zoom/process_caption")
async def process_caption(request: dict):
    """Take a caption and run it through Koan"""
    caption = request.get("caption", "")
    if not caption:
        return {"error": "No caption provided"}

    result = assistant.generate_answer(caption)
    return result

@app.get("/api/answers")
async def get_answers():
    """Get the latest answer from in-memory store"""
    global latest_answer
    return latest_answer

@app.post("/rtms/transcript")
async def rtms_transcript(request: dict):
    """Receive transcript from RTMS WebSocket, process it, and store the answer"""
    global latest_answer

    transcript = request.get("transcript", "")
    if not transcript:
        return {"error": "No transcript provided"}

    try:
        # Process the transcript through KoanAssistant
        result = assistant.generate_answer(transcript)

        # Store the latest answer with a new ID
        latest_answer = {
            "id": str(uuid.uuid4()),
            "caption": transcript,
            "answer": result,
            "timestamp": time.time()
        }

        print(f"RTMS transcript processed: {transcript[:100]}... -> Answer stored")
        return {
            "status": "ok",
            "id": latest_answer["id"],
            "answer": result
        }
    except Exception as e:
        print(f"RTMS transcript error: {e}")
        return {"status": "error", "error": str(e)}
