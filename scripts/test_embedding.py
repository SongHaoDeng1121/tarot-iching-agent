
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

client = OpenAI(
    api_key=os.environ["SILICONFLOW_API_KEY"],
    base_url="https://api.siliconflow.cn/v1",
)

response = client.embeddings.create(
    model="BAAI/bge-m3",
    input="The Knight of Cups represents emotional expression."
)

vector = response.data[0].embedding

print("Embedding API: SUCCESS")
print("Vector dimensions:", len(vector))
print("First 5 values:", vector[:5])
