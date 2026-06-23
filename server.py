from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from contextlib import asynccontextmanager
import json
import os
import time
import hmac
import hashlib
import base64
import requests
import uuid
import asyncio
import websockets
from retrieval_pipeline import KoanAssistant

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Server lifespan context manager"""
    # Startup
    print("STARTUP: Connecting to Zoom WebSocket...")
    asyncio.create_task(connect_zoom_websocket())
    yield
    # Shutdown
    print("SHUTDOWN: Server closing...")

app = FastAPI(lifespan=lifespan)

# In-memory store for latest answer
latest_answer = {
    "id": str(uuid.uuid4()),
    "caption": "",
    "answer": {"answer": ""},
    "timestamp": 0
}

# Track active RTMS WebSocket connections
rtms_connections = {}

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

# Zoom environment variables
ZOOM_WEBSOCKET_SECRET = os.getenv("ZOOM_WEBSOCKET_SECRET", "xHLWvrVmTt6xtFe36UxaMw")
ZOOM_EVENT_WEBSOCKET_URL = "wss://ws.zoom.us/ws?subscriptionId=ncuuFdj6TOOvx4hjjoxMVQ"

# Track Zoom event WebSocket connection
zoom_event_websocket = None

async def connect_zoom_websocket():
    """Connect to Zoom's event WebSocket and listen for meeting events"""
    global zoom_event_websocket

    try:
        print(f"[ZOOM] Attempting to connect to: {ZOOM_EVENT_WEBSOCKET_URL}")
        async with websockets.connect(ZOOM_EVENT_WEBSOCKET_URL) as websocket:
            zoom_event_websocket = websocket
            print("[ZOOM] ✓ Connected to event WebSocket successfully")

            # Start heartbeat task
            print("[ZOOM] Starting heartbeat task...")
            heartbeat_task = asyncio.create_task(send_heartbeat(websocket))

            try:
                # Listen for incoming messages
                print("[ZOOM] Listening for events...")
                async for message_str in websocket:
                    try:
                        message = json.loads(message_str)
                        event = message.get('event', 'unknown')
                        print(f"[ZOOM] Event received: {event}")

                        # Handle meeting.rtms_started event
                        if event == "meeting.rtms_started":
                            print("[ZOOM] Processing meeting.rtms_started event")
                            payload = message.get("payload", {})
                            server_urls = payload.get("server_urls", [])
                            meeting_id = payload.get("meeting_id", "unknown")

                            print(f"[ZOOM] Meeting ID: {meeting_id}")
                            print(f"[ZOOM] Server URLs count: {len(server_urls) if server_urls else 0}")

                            if server_urls:
                                # Get the first server URL for RTMS
                                rtms_url = server_urls[0] if isinstance(server_urls, list) else server_urls
                                access_token = payload.get("access_token", "")

                                print(f"[ZOOM] RTMS URL: {rtms_url[:50]}...")
                                print(f"[ZOOM] Access token present: {bool(access_token)}")

                                if rtms_url and access_token:
                                    print(f"[ZOOM] ✓ Starting RTMS connection for meeting {meeting_id}")
                                    # Connect to RTMS WebSocket
                                    asyncio.create_task(connect_to_rtms(rtms_url, access_token, meeting_id))
                                else:
                                    print(f"[ZOOM] ✗ Missing RTMS URL or token")
                            else:
                                print(f"[ZOOM] ✗ No server URLs in payload")
                        else:
                            print(f"[ZOOM] Ignoring event type: {event}")
                    except json.JSONDecodeError as e:
                        print(f"[ZOOM] ✗ JSON parse error: {str(e)[:100]}")
                    except Exception as e:
                        print(f"[ZOOM] ✗ Error processing event: {e}")
            finally:
                print("[ZOOM] Message listening stopped, cancelling heartbeat...")
                heartbeat_task.cancel()
                zoom_event_websocket = None
    except Exception as e:
        print(f"[ZOOM] ✗ WebSocket connection error: {e}")
        zoom_event_websocket = None
        await asyncio.sleep(5)  # Wait before reconnecting
        print("[ZOOM] Attempting to reconnect in background...")
        asyncio.create_task(connect_zoom_websocket())

async def send_heartbeat(websocket):
    """Send heartbeat to keep Zoom event WebSocket alive"""
    try:
        print("[HEARTBEAT] Starting heartbeat loop (30s interval)...")
        while True:
            await asyncio.sleep(30)
            heartbeat = {"module": "heartbeat"}
            await websocket.send(json.dumps(heartbeat))
            print("[HEARTBEAT] ✓ Heartbeat sent")
    except asyncio.CancelledError:
        print("[HEARTBEAT] Task cancelled")
    except Exception as e:
        print(f"[HEARTBEAT] ✗ Error: {e}")

async def connect_to_rtms(rtms_url: str, access_token: str, meeting_id: str):
    """Connect to RTMS WebSocket and process transcript messages"""
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        print(f"[RTMS] Connecting for meeting {meeting_id}...")
        print(f"[RTMS] URL: {rtms_url[:50]}...")
        async with websockets.connect(rtms_url, extra_headers=headers) as websocket:
            print(f"[RTMS] ✓ Connected for meeting {meeting_id}")
            rtms_connections[meeting_id] = websocket

            try:
                print(f"[RTMS] Listening for transcripts on meeting {meeting_id}...")
                async for message_str in websocket:
                    try:
                        message = json.loads(message_str)
                        print(f"[RTMS] Message received (type: {message.get('type', 'unknown')})")
                        await process_rtms_message(message, meeting_id)
                    except json.JSONDecodeError as e:
                        print(f"[RTMS] ✗ JSON parse error: {str(e)[:100]}")
                    except Exception as e:
                        print(f"[RTMS] ✗ Error processing message: {e}")
            finally:
                rtms_connections.pop(meeting_id, None)
                print(f"[RTMS] ✓ Connection closed for meeting {meeting_id}")
    except Exception as e:
        print(f"[RTMS] ✗ Connection error for meeting {meeting_id}: {e}")
        rtms_connections.pop(meeting_id, None)

@app.on_event("startup")
async def startup_event():
    """Start Zoom event WebSocket connection on server startup"""
    print("Server starting up...")
    asyncio.create_task(connect_to_zoom_events())

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

@app.head("/zoom/sidebar")
async def head_zoom_sidebar():
    """Handle HEAD requests for /zoom/sidebar endpoint"""
    return Response(status_code=200)

@app.post("/api/answer")
async def get_answer(request: dict):
    result = assistant.generate_answer(request.get("text", ""))
    return result

ZOOM_WEBHOOK_SECRET = os.getenv("ZOOM_WEBHOOK_SECRET", "hnEpcWPYTmOR5wg9R-YtKw")

def validate_zoom_webhook(request_body: bytes, signature: str, timestamp: str) -> bool:
    """Validate webhook authenticity using HMAC"""
    if not signature or not timestamp:
        return False

    # Reconstruct the signed content: timestamp + body
    message = f"{timestamp}{request_body.decode()}"

    # Compute HMAC SHA256
    expected_signature = "v0=" + hmac.new(
        ZOOM_WEBHOOK_SECRET.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    # Compare signatures securely
    return hmac.compare_digest(signature, expected_signature)

async def process_rtms_message(message: dict, meeting_id: str):
    """Process a message from RTMS WebSocket"""
    global latest_answer

    # Look for transcript in message
    transcript = None
    if message.get("msg_type") == "TRANSCRIPT":
        print(f"[RTMS] Found TRANSCRIPT msg_type")
        transcript = message.get("transcript", "")
    elif "transcript" in message:
        print(f"[RTMS] Found transcript field in message")
        transcript = message.get("transcript", "")

    if transcript and isinstance(transcript, str) and transcript.strip():
        print(f"[RTMS] ✓ Processing transcript: {transcript[:100]}...")
        try:
            print(f"[RTMS] Calling assistant.generate_answer()...")
            result = assistant.generate_answer(transcript)
            latest_answer = {
                "id": str(uuid.uuid4()),
                "caption": transcript,
                "answer": result,
                "timestamp": time.time()
            }
            print(f"[RTMS] ✓ Answer stored with ID: {latest_answer['id']}")
        except Exception as e:
            print(f"[RTMS] ✗ Error processing transcript: {e}")
    else:
        print(f"[RTMS] No transcript found in message or empty")

@app.post("/zoom/webhook")
async def zoom_webhook(request: Request):
    """Handle Zoom webhook events with HMAC validation"""
    body = await request.body()

    try:
        data = json.loads(body)

        # Handle endpoint.url_validation (URL validation challenge during setup)
        # This doesn't require signature validation yet since it's part of registration
        if data.get("event") == "endpoint.url_validation":
            plain_token = data.get("payload", {}).get("plainToken", "")
            if plain_token:
                # Encrypt plainToken with ZOOM_WEBHOOK_SECRET using HMAC SHA256
                encrypted_token = hmac.new(
                    ZOOM_WEBHOOK_SECRET.encode(),
                    plain_token.encode(),
                    hashlib.sha256
                ).hexdigest()
                print(f"URL validation successful")
                return {
                    "plainToken": plain_token,
                    "encryptedToken": encrypted_token
                }

        # Validate webhook signature for all other events
        signature = request.headers.get("x-zm-signature")
        timestamp = request.headers.get("x-zm-request-timestamp")

        if not validate_zoom_webhook(body, signature, timestamp):
            print("Invalid webhook signature")
            return {"status": "error", "message": "Invalid signature"}

        # Handle webhook challenge for verification
        if "challenge" in data:
            return {
                "challengeToken": data["challenge"]
            }

        event = data.get("event")
        payload = data.get("payload", {})
        meeting_id = payload.get("meeting_id", "unknown")

        # Handle RTMS started event
        if event == "meeting.rtms_started":
            ws_url = payload.get("ws_url")
            access_token = payload.get("access_token")

            if ws_url and access_token:
                print(f"RTMS started for meeting {meeting_id}")
                # Start background WebSocket connection
                asyncio.create_task(connect_to_rtms(ws_url, access_token, meeting_id))
                return {"status": "ok", "message": "RTMS connection started"}
            else:
                print(f"Missing ws_url or access_token for meeting {meeting_id}")
                return {"status": "error", "message": "Missing RTMS parameters"}

        # Handle RTMS stopped event
        elif event == "meeting.rtms_stopped":
            print(f"RTMS stopped for meeting {meeting_id}")
            # Close WebSocket if exists
            if meeting_id in rtms_connections:
                await rtms_connections[meeting_id].close()
            return {"status": "ok", "message": "RTMS connection stopped"}

        # Handle other events
        elif event == "meeting.transcript_caption_created":
            caption = payload.get("object", {}).get("caption", "")
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
    """Get the latest answer from in-memory store if valid"""
    global latest_answer

    # Only return if answer has non-empty answer string and confidence > 0
    if (latest_answer.get("answer") and
        isinstance(latest_answer["answer"], dict) and
        latest_answer["answer"].get("answer") and
        isinstance(latest_answer["answer"]["answer"], str) and
        latest_answer["answer"]["answer"].strip() != "" and
        latest_answer["answer"].get("confidence", 0) > 0):
        return latest_answer

    # Return empty answer structure if no valid answer yet
    return {
        "id": str(uuid.uuid4()),
        "caption": "",
        "answer": {"answer": ""},
        "timestamp": 0
    }

@app.post("/rtms/transcript")
async def rtms_transcript(request: dict):
    """Receive transcript from RTMS WebSocket, process it, and store the answer"""
    global latest_answer

    # Extract transcript from request
    transcript = request.get("transcript", "") if isinstance(request, dict) else ""

    if not transcript or not isinstance(transcript, str) or transcript.strip() == "":
        return {"error": "No valid transcript provided"}

    try:
        # Use exact same logic as /api/answer endpoint
        result = assistant.generate_answer(transcript)

        # Store the latest answer with a new ID and timestamp
        latest_answer = {
            "id": str(uuid.uuid4()),
            "caption": transcript,
            "answer": result,
            "timestamp": time.time()
        }

        print(f"RTMS transcript processed: {transcript[:100]}...")
        print(f"  Answer stored with ID: {latest_answer['id']}")

        return {
            "status": "ok",
            "id": latest_answer["id"],
            "answer": result
        }
    except Exception as e:
        print(f"RTMS transcript error: {e}")
        return {"status": "error", "error": str(e)}
