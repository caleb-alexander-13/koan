from pinecone import Pinecone
from anthropic import Anthropic
import os
import json
from dotenv import load_dotenv

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("cavalli-knowledge")
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

with open("knowledge_base.json") as f:
    kb = json.load(f)

facts = kb["facts"]

print(f"Embedding {len(facts)} facts...")

vectors = []
for i, fact in enumerate(facts):
    text = f"{fact['topic']}: {fact['text']}"
    
    # Use Pinecone's built-in inference to embed
    embedding = pc.inference.embed(
        model="multilingual-e5-large",
        inputs=[text],
        parameters={"input_type": "passage"}
    )
    
    vectors.append({
        "id": f"fact_{i}",
        "values": embedding[0].values,
        "metadata": {"topic": fact["topic"], "text": fact["text"]}
    })
    print(f"  Embedded: {fact['topic']}")

index.upsert(vectors=vectors, namespace="facts")
print(f"\nDone. {len(vectors)} facts in Pinecone.")
