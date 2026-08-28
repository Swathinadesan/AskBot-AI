"""
MongoDB connection for Placementor AI.

The connection string now comes from the MONGO_URI environment variable
instead of being hardcoded, so the same code works locally (.env file)
and in production (Render environment variables) without any changes.

Collections are unchanged from the original project:
- users          : registered student accounts
- admins         : admin accounts
- chat_history    : every chat exchange (question, answer, source, etc.)
- questions       : legacy collection populated by scripts/upload_pdf.py
- qa_data         : the live knowledge base the chatbot searches first
"""

import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConfigurationError, PyMongoError

load_dotenv()

MONGO_URI = os.environ.get("MONGO_URI", "").strip()

if not MONGO_URI:
    sys.exit(
        "MONGO_URI is not set.\n"
        "Create a .env file in the project root (see .env.example) and set:\n"
        "  MONGO_URI=your-mongodb-connection-string\n"
        "or export MONGO_URI as an environment variable before starting the app."
    )

try:
   client = MongoClient("mongodb+srv://placementuser:PlacementAI47@cluster0.aqpcxah.mongodb.net/?appName=Cluster0")
except ConfigurationError as exc:
    sys.exit(f"MONGO_URI looks invalid: {exc}")

db = client["placement_ai"]

users = db["users"]
admins = db["admins"]
chat_collection = db["chat_history"]
qa_data = db["qa_data"]
resumes = db["resumes"]
documents = db["documents"]

def ping():
    """Small helper used at startup / by scripts to confirm connectivity."""
    try:
        client.admin.command("ping")
        return True
    except PyMongoError:
        return False
