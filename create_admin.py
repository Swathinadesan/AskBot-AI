from werkzeug.security import generate_password_hash
from db import admins

username = "admin"
password = "admin123"

existing = admins.find_one({"username": username})

if existing:
    print("Admin already exists!")
else:
    admins.insert_one({
        "username": username,
        "password": generate_password_hash(password)
    })

    print("Admin created successfully!")
    print("Username:", username)
    print("Password:", password)