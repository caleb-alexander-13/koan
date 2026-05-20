import json
import os
from pinecone import Pinecone

# Load knowledge base
with open('knowledge_base.json') as f:
    kb = json.load(f)

# Initialize Pinecone
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index(os.getenv("PINECONE_INDEX", "cavalli-knowledge"))

# Store facts in Pinecone
vectors = []
for i, fact in enumerate(kb['facts']):
    vectors.append((
        f"fact-{i}",
        [0.1] * 1536,  # Placeholder vector
        {"text": fact['text'], "topic": fact['topic']}
    ))

index.upsert(vectors=vectors)
print(f"Loaded {len(kb['facts'])} facts into Pinecone")
