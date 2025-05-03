from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import sqlite3
from datetime import datetime
import hashlib
import json

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
def init_db():
    conn = sqlite3.connect('last_resort.db')
    c = conn.cursor()
    
    # Create users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    
    # Create pairs table
    c.execute('''
        CREATE TABLE IF NOT EXISTS pairs (
            pair_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_a_id INTEGER NOT NULL,
            user_b_id INTEGER NOT NULL,
            FOREIGN KEY (user_a_id) REFERENCES users (user_id),
            FOREIGN KEY (user_b_id) REFERENCES users (user_id)
        )
    ''')
    
    # Create notes table
    c.execute('''
        CREATE TABLE IF NOT EXISTS notes (
            note_id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            entry TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (pair_id) REFERENCES pairs (pair_id),
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_db()

# Models
class UserRegister(BaseModel):
    username: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class User(BaseModel):
    user_id: int
    username: str
    email: str
    pair_ids: List[int]

class NoteEntry(BaseModel):
    pair_id: int
    username: str
    entry: str
    date: str

# Helper functions
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_by_email(email: str):
    conn = sqlite3.connect('last_resort.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE email = ?', (email,))
    user = c.fetchone()
    conn.close()
    return user

def get_user_pairs(user_id: int):
    conn = sqlite3.connect('last_resort.db')
    c = conn.cursor()
    c.execute('''
        SELECT pair_id FROM pairs 
        WHERE user_a_id = ? OR user_b_id = ?
    ''', (user_id, user_id))
    pairs = [row[0] for row in c.fetchall()]
    conn.close()
    return pairs

# Routes
@app.post("/register")
async def register(user_data: UserRegister):
    conn = sqlite3.connect('last_resort.db')
    c = conn.cursor()
    
    try:
        # Check if username or email already exists
        c.execute('SELECT * FROM users WHERE username = ? OR email = ?', 
                 (user_data.username, user_data.email))
        if c.fetchone():
            raise HTTPException(status_code=400, detail="Username or email already exists")
        
        # Insert new user
        c.execute('''
            INSERT INTO users (username, email, password_hash)
            VALUES (?, ?, ?)
        ''', (user_data.username, user_data.email, hash_password(user_data.password)))
        
        conn.commit()
        return {"message": "Registration successful"}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.post("/login")
async def login(user_data: UserLogin):
    user = get_user_by_email(user_data.email)
    if not user or user[3] != hash_password(user_data.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    pair_ids = get_user_pairs(user[0])
    return {
        "user": {
            "user_id": user[0],
            "username": user[1],
            "email": user[2],
            "pair_ids": pair_ids
        }
    }

@app.post("/create_pair")
async def create_pair(user_a_username: str, user_b_username: str):
    conn = sqlite3.connect('last_resort.db')
    c = conn.cursor()
    
    try:
        # Get user IDs
        c.execute('SELECT user_id FROM users WHERE username = ?', (user_a_username,))
        user_a = c.fetchone()
        c.execute('SELECT user_id FROM users WHERE username = ?', (user_b_username,))
        user_b = c.fetchone()
        
        if not user_a or not user_b:
            raise HTTPException(status_code=404, detail="One or both users not found")
        
        # Create pair
        c.execute('''
            INSERT INTO pairs (user_a_id, user_b_id)
            VALUES (?, ?)
        ''', (user_a[0], user_b[0]))
        
        pair_id = c.lastrowid
        conn.commit()
        return {"pair_id": pair_id}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.put("/add_note_entry")
async def add_note_entry(pair_id: int, date: str, username: str, entry: str):
    conn = sqlite3.connect('last_resort.db')
    c = conn.cursor()
    
    try:
        # Get user_id from username
        c.execute('SELECT user_id FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user[0]
        
        # Check if note exists for this date
        c.execute('''
            SELECT note_id FROM notes 
            WHERE pair_id = ? AND user_id = ? AND date = ?
        ''', (pair_id, user_id, date))
        existing_note = c.fetchone()
        
        now = datetime.now().isoformat()
        
        if existing_note:
            # Update existing note
            c.execute('''
                UPDATE notes 
                SET entry = ?, updated_at = ?
                WHERE note_id = ?
            ''', (entry, now, existing_note[0]))
        else:
            # Create new note
            c.execute('''
                INSERT INTO notes (pair_id, user_id, date, entry, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (pair_id, user_id, date, entry, now))
        
        conn.commit()
        return {"message": "Note saved successfully"}
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

@app.get("/get_partner_note")
async def get_partner_note(pair_id: int, username: str):
    conn = sqlite3.connect('last_resort.db')
    c = conn.cursor()
    
    try:
        # Get user_id from username
        c.execute('SELECT user_id FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_id = user[0]
        
        # Get partner's user_id
        c.execute('''
            SELECT user_a_id, user_b_id FROM pairs 
            WHERE pair_id = ? AND (user_a_id = ? OR user_b_id = ?)
        ''', (pair_id, user_id, user_id))
        pair = c.fetchone()
        if not pair:
            raise HTTPException(status_code=404, detail="Pair not found")
        
        partner_id = pair[1] if pair[0] == user_id else pair[0]
        
        # Get partner's username
        c.execute('SELECT username FROM users WHERE user_id = ?', (partner_id,))
        partner = c.fetchone()
        if not partner:
            raise HTTPException(status_code=404, detail="Partner not found")
        
        # Get partner's latest note
        c.execute('''
            SELECT entry, updated_at FROM notes 
            WHERE pair_id = ? AND user_id = ? 
            ORDER BY date DESC LIMIT 1
        ''', (pair_id, partner_id))
        note = c.fetchone()
        
        if note:
            return {
                "partner": partner[0],
                "entry": note[0],
                "updated": note[1]
            }
        else:
            return {
                "partner": partner[0],
                "entry": None,
                "message": "No note found"
            }
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 

from fastapi.responses import FileResponse

@app.get("/download_db")
def download_db():
       return FileResponse("database.db", filename="database.db")