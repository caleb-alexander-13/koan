from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import os
import time
import hmac
import hashlib
import base64
import requests
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
    return {"status": "Koan server is running", "version": "0.1.0"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/demo")
async def get_demo():
    with open("voice_app_demo.html") as f:
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
