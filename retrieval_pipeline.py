import os
import json
from anthropic import Anthropic
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv(dotenv_path='/Users/calebaalexander/koan/.env')

class KoanAssistant:
    def __init__(self):
        self.client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.model = "claude-haiku-4-5-20251001"
        pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
        self.index = pc.Index("cavalli-knowledge")
        self.pc = pc

    def retrieve(self, query):
        try:
            embedding = self.pc.inference.embed(
                model="multilingual-e5-large",
                inputs=[query],
                parameters={"input_type": "query"}
            )
            results = self.index.query(
                vector=embedding[0].values,
                top_k=2,
                namespace="facts",
                include_metadata=True
            )
            matches = results.get("matches", [])
            if matches and matches[0]["score"] > 0.5:
                return matches[0]["metadata"]["text"]
        except Exception as e:
            print(f"Retrieval error: {e}")
        return None

    def generate_answer(self, question):
        fact = self.retrieve(question)

        if fact:
            prompt = f"""Fact: "{fact}"
Question: "{question}"

Reply in this exact format:
[2-5 word direct answer]
...
[One supporting sentence under 20 words]"""
        else:
            prompt = f"""Question about Cavalli venue: "{question}"
Reply: "I don't have that information"
... Please contact Cavalli directly for details."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=80,
                messages=[{"role": "user", "content": prompt}]
            )
            answer = response.content[0].text.strip()
        except Exception as e:
            answer = f"Error: {str(e)}"

        return {
            "question": question,
            "answer": answer,
            "confidence": 90 if fact else 0
        }
