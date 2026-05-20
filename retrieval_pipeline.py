import json
import os
from anthropic import Anthropic
from pinecone import Pinecone

class KoanAssistant:
    def __init__(self):
        self.client = Anthropic()
        self.pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index = self.pc.Index(os.getenv("PINECONE_INDEX", "cavalli-knowledge"))
        self.transcript_buffer = []
        
    def process_transcript_chunk(self, text, speaker):
        self.transcript_buffer.append({"speaker": speaker, "text": text})
        
        # Check if this looks like a question
        if not any(q in text.lower() for q in ["?", "what", "how", "when", "where", "why"]):
            return None
        
        # Get answer from vector DB
        try:
            results = self.index.query(text, top_k=3, include_metadata=True)
            context = "\n".join([m["metadata"].get("text", "") for m in results.get("matches", [])])
        except:
            context = ""
        
        if not context:
            return None
        
        # Generate answer with Claude
        response = self.client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": f"Answer this question based on the context below. Be concise.\n\nQuestion: {text}\n\nContext: {context}"
                }
            ]
        )
        
        answer = response.content[0].text
        confidence = 75  # Placeholder
        
        return {
            "question": text,
            "answer": answer,
            "confidence": confidence
        }
