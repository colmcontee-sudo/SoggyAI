from flask import Flask, request, jsonify
from flask_cors import CORS
from mem0 import Memory
import requests
import json
import os
import hashlib

app = Flask(__name__)
CORS(app) 

DB_FILE = "soggy_accounts.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=4)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# Configure Mem0
config = {
    "llm": {
        "provider": "openai",
        "config": {
            "api_key": "not-needed", 
            "openai_base_url": "http://127.0.0.1:1234/v1",
            "model": "local-model" 
        }
    },
    "embedder": {
        "provider": "huggingface",
        "config": {
            "model": "sentence-transformers/all-MiniLM-L6-v2"
        }
    }
}

print("🧠 Initializing Local Memory Bank...")
memory = Memory.from_config(config)
print("✅ Memory Bank Ready!")

@app.route("/sync", methods=["POST"])
def sync_account():
    db = load_db()
    data = request.json
    username = data.get("username", "").lower()
    password = data.get("password", "")
    
    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    hashed = hash_password(password)

    # If user exists, check password
    if username in db:
        if db[username].get("password") != hashed:
            return jsonify({"error": "Invalid password"}), 401
        
        # If it's just a login check (no chats sent), return the data
        if "chats" not in data:
            return jsonify(db[username])
    else:
        # Create new user
        db[username] = {
            "password": hashed,
            "chats": [],
            "memory": {"about": "", "respond": ""}
        }

    # If chats were sent, save them
    if "chats" in data:
        db[username]["chats"] = data.get("chats", [])
        db[username]["memory"] = data.get("memory", {})
    
    save_db(db)
    return jsonify(db[username])

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    messages = data.get("messages", [])
    username = data.get("username", "guest").lower()
    
    user_message = ""
    if messages and messages[-1]["role"] == "user":
        content = messages[-1]["content"]
        user_message = content if isinstance(content, str) else next((i["text"] for i in content if i["type"] == "text"), "")

    if user_message.strip():
        memory.add(user_message, user_id=username)
        past_memories = memory.search(user_message, user_id=username)
        memory_context = "\n".join([m['memory'] for m in past_memories])
        
        if memory_context and messages[0]["role"] == "system":
            messages[0]["content"] += f"\n\n--- USER MEMORY ---\n{memory_context}"

    payload = {"model": "local-model", "messages": messages, "temperature": 0.7}
    
    try:
        response = requests.post("http://127.0.0.1:1234/v1/chat/completions", json=payload)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(port=5000)