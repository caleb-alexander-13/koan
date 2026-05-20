import json
import os
from anthropic import Anthropic

class KoanAssistant:
    def __init__(self, knowledge_base_path="knowledge_base.json"):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-haiku-4-5-20251001"
        
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
        
        return matching_facts[0] if matching_facts else None
    
    def generate_answer(self, question):
        fact = self.retrieve(question)
        
        if fact:
            # Fact found—use it directly with minimal formatting
            prompt = f"""Given this fact: "{fact}"

Answer the question: "{question}"

Respond ONLY with:
1. A 2-3 word direct answer (Yes/No/Time/Price etc)
2. "..." on next line
3. ONE short sentence max (under 20 words)

Example Q: What time does the wedding have to end?
Example Fact: Amplified music stops 10pm. Hard close 11pm.
Example A:
11pm
... Amplified music must stop by 10pm.

Now answer:"""
        else:
            # No fact found
            prompt = f"""Question: "{question}"

Respond ONLY with:
"Unknown"
... Need more information about this venue."""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}]
            )
            answer = response.content[0].text.strip()
        except Exception as e:
            answer = f"ERROR: {str(e)}"
        
        return {
            "question": question,
            "answer": answer,
            "confidence": 85 if fact else 0
        }
