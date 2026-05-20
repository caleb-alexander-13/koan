import json
from anthropic import Anthropic

class KoanAssistant:
    def __init__(self, knowledge_base_path="knowledge_base.json"):
        self.client = Anthropic()
        self.model = "claude-opus-4-20250805"
        
        try:
            with open(knowledge_base_path, 'r') as f:
                self.kb = json.load(f)
        except:
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
            answer = "Unable to generate answer"
        
        return {
            "question": question,
            "answer": answer,
            "confidence": 75
        }
