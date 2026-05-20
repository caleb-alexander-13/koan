import json
import os
from anthropic import Anthropic

class KoanAssistant:
    def __init__(self):
        self.client = Anthropic()
        
        # Load knowledge base
        with open('knowledge_base.json') as f:
            self.kb = json.load(f)
    
    def process_transcript_chunk(self, text, speaker):
        # Check if this looks like a question
        if not any(q in text.lower() for q in ["?", "what", "how", "when", "where", "why", "can", "do", "are"]):
            return None
        
        # Simple keyword matching for context
        text_lower = text.lower()
        matching_facts = []
        for fact in self.kb['facts']:
            if any(keyword in text_lower for keyword in fact['text'].lower().split()):
                matching_facts.append(fact['text'])
        
        context = "\n".join(matching_facts) if matching_facts else ""
        
        if not context:
            return None
        
        # Generate answer with Claude
        response = self.client.messages.create(
            model="claude-opus-4-20250514",
            max_tokens=300,
            messages=[
                {
                    "role": "user",
                    "content": f"Answer this question concisely based on the context. Question: {text}\n\nContext: {context}"
                }
            ]
        )
        
        answer = response.content[0].text
        confidence = 75
        
        return {
            "question": text,
            "answer": answer,
            "confidence": confidence
        }
