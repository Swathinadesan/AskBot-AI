from pymongo import MongoClient
from werkzeug.security import generate_password_hash

client = MongoClient("mongodb://localhost:27017/")
client["placement_ai"]["admins"].update_one(
    {"username": "admin"},
    {"$set": {"password": generate_password_hash("admin1234")}}
)
print("done")