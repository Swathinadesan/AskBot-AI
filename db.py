"""
MongoDB connection for Placementor AI.

Uses MONGO_URI from environment variables.
Works locally with .env and on Render with Environment Variables.
"""

import os
import sys

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConfigurationError, PyMongoError

# Load .env when running locally
load_dotenv()

# Read MongoDB connection string
MONGO_URI = os.environ.get("MONGO_URI", "").strip()

# Check whether MONGO_URI exists
if not MONGO_URI:
    sys.exit(
        "MONGO_URI is not set.\n"
        "Set MONGO_URI in your .env file locally or "
        "in Render Environment Variables."
    )

# ---------------------------------------------------------
# TEMPORARY DEBUG
# ---------------------------------------------------------
# This does NOT print your password.
print("========================================")
print("MongoDB Environment Check")
print("MONGO_URI exists:", bool(MONGO_URI))
print("MONGO_URI starts with:", MONGO_URI[:30])
print("========================================")


# ---------------------------------------------------------
# MongoDB CONNECTION
# ---------------------------------------------------------
try:
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=10000
    )

except ConfigurationError as exc:
    sys.exit(f"MONGO_URI looks invalid: {exc}")


# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------
db = client["placement_ai"]


# ---------------------------------------------------------
# COLLECTIONS
# ---------------------------------------------------------
users = db["users"]

admins = db["admins"]

chat_collection = db["chat_history"]

qa_data = db["qa_data"]

resumes = db["resumes"]

documents = db["documents"]


# ---------------------------------------------------------
# CONNECTION TEST
# ---------------------------------------------------------
def ping():
    """
    Check whether MongoDB Atlas is reachable.
    Returns True if connection works.
    """

    try:
        client.admin.command("ping")

        print("MongoDB Atlas connection: SUCCESS")

        return True

    except PyMongoError as exc:

        print("MongoDB Atlas connection: FAILED")
        print("MongoDB error:", exc)

        return False
