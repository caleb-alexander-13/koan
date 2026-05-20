import json
import os
from anthropic import Anthropic

class KoanAssistant:
    def __init__(self, knowledge_base_path="knowledge_base.json"):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-haiku-4-5-20251001"  # Fastest model
        
        try:
            with open(knowledge_base_path, 'r') as f:
                self.kb = json.load(f)
        except Exception as e:
            print(f"KB load error: {e}")
            self.kb = {"facts": []}
    
    def retrieve(self, query):
        query_lower = query.lower()
        matching_facts = []
        
        for fact in self.kb.get('facts', []):
            fact_text = fact.get('text', '').lower()
            if any(word in query_lower for word in fact_text.split()):
                matching_facts.append(fact['text'])
        
        return ' '.join(matching_facts[:3]) if matching_facts else "No specific information found."
    
    def generate_answer(self, question):
        context = self.retrieve(question)
        
        prompt = f"""Answer this question about a venue: {question}

Context: {context}

Respond with:
1. Short answer (1-3 words)
2. Then "..." 
3. Then one detail

Example: No ... Fireworks not allowed. LED displays are alternatives.

Answer:"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt}]
            )
            answer = response.content[0].text.strip()
        except Exception as e:
            answer = f"ERROR: {str(e)}"
            print(f"API call failed: {e}")
        
        return {
            "question": question,
            "answer": answer,
            "confidence": 75
        }
