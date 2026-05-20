from fastapi import FastAPI
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import json
import os
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
    text = request.get("text", "")
    if not text:
        return JSONResponse({"error": "No text provided"}, status_code=400)
    
    result = assistant.generate_answer(text)
    return result
