import json
import os
from anthropic import Anthropic

class KoanAssistant:
    def __init__(self, knowledge_base_path="knowledge_base.json"):
        self.client = Anthropic()
        self.model = "claude-opus-4-20250805"
        
        with open(knowledge_base_path, 'r') as f:
            self.kb = json.load(f)
    
    def retrieve(self, query):
        """Simple keyword matching retrieval"""
        query_lower = query.lower()
        matching_facts = []
        
        for fact in self.kb.get('facts', []):
            fact_text = fact.get('text', '').lower()
            keywords = fact_text.split()
            
            if any(keyword in query_lower for keyword in keywords):
                matching_facts.append(fact['text'])
        
        return ' '.join(matching_facts[:3]) if matching_facts else "No relevant information found"
    
    def generate_answer(self, question):
        """Generate answer with Claude"""
        context = self.retrieve(question)
        
        prompt = f"""Given this question about a venue: "{question}"

Using this information: {context}

Respond with ONLY:
1. A direct answer (1-3 words max): Yes, No, or a short phrase
2. Optional: "..." followed by one relevant detail if helpful

Example:
No
... Fireworks not allowed. LED displays and sparklers are alternatives.

Now answer:"""
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        
        answer = response.content[0].text.strip()
        confidence = 75
        
        return {
            "question": question,
            "answer": answer,
            "confidence": confidence
        }

def main():
    assistant = KoanAssistant()
    
    test_questions = [
        "Are fireworks allowed?",
        "What's the cancellation policy?",
        "What's your capacity?"
    ]
    
    for q in test_questions:
        result = assistant.generate_answer(q)
        print(f"\nQ: {result['question']}")
        print(f"A: {result['answer']}")
        print(f"Confidence: {result['confidence']}%")

if __name__ == "__main__":
    main()