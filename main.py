from sqlmodel import Field, Session, SQLModel, create_engine, select
from datetime import datetime
from datetime import date
from typing import Optional
from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException
import jwt
from datetime import datetime, timedelta
from typing import Union
from passlib.context import CryptContext

class User(SQLModel, table=True):
    user_id : int = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)
    email: str = Field(nullable=False, unique=True, index=True)
    password_hash : str
    created_at: datetime
    
class pair(SQLModel, table = True):
    pair_id:int = Field(default=None, primary_key=True)
    user_a_name : str
    user_b_name : str
    created_pair_at : datetime

class note(SQLModel, table=True):
    note_id: Optional[int] = Field(default=None, primary_key=True)
    pair_id: int = Field(foreign_key="pair.pair_id")
    date: date

    user_a_id: Optional[int] = Field(default=None, foreign_key="user.user_id")
    user_b_id: Optional[int] = Field(default=None, foreign_key="user.user_id")
    user_a_entry: Optional[str] = None
    user_b_entry: Optional[str] = None
    user_a_updated: Optional[datetime] = None
    user_b_updated: Optional[datetime] = None
    
sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

connect_args = {"check_same_thread":False}
engine = create_engine(sqlite_url, connect_args=connect_args)

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)
    
SECRET_KEY = "your_secret_key_here"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

def create_access_token(data: dict, expires_delta: Union[timedelta, None]= None)-> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow()+expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp":expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload  # Returns the decoded payload
    except jwt.PyJWTError:
        return None  # Returns None if token is invalid

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_session():
    with Session(engine) as session:
        yield session

SessionDep = Annotated[Session, Depends(get_session)]

app = FastAPI()
@app.get("/")
def read_root():
    return {"message": "Welcome to the FastAPI app!"}
from fastapi.responses import FileResponse





@app.on_event("startup")

def on_startup():
    create_db_and_tables()
@app.post("/register")
def create_user(username: str, email: str, password: str, session: SessionDep):
    
    existing_user = session.exec(select(User).where(User.email == email)).first()
    if existing_user:
        raise HTTPException(status_code = 400, detail = "Email already registeres")
    
    hashed_password = hash_password(password)
    new_user = User(
        username = username,
        email=email,
        password_hash = hashed_password,
        created_at = datetime.utcnow()
    )
    
    
    session.add(new_user)
    session.commit()
    session.refresh(new_user)
    return {"message":"Registered Succesfully", "user_id": new_user.user_id}
     
@app.post("/login")
def get_user(email: str, password: str, session: SessionDep):
    
    user_email = session.exec(select(User).where(User.email==email)).first()
    
    if user_email is None:
         raise HTTPException(status_code = 400, detail = "Email not registered")
    
    if not verify_password(password, user_email.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")
    
    token = create_access_token(data = {"sub": user_email.email})
    return{
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user_email.user_id,
            "username": user_email.username,
            "email": user_email.email,
        }
    }
    
@app.post("/create_pair")
def create_pair(user_a_username: str, user_b_username: str, session: SessionDep):
    
    user_a = session.exec(select(User).where(User.username==user_a_username)).first()
    user_b = session.exec(select(User).where(User.username==user_b_username)).first()
    
    if user_a is None:
        raise HTTPException(status_code = 400, detail = "User A does not exists" )
    if user_b is None:
        raise HTTPException(status_code = 401, detail = "User B does not exists" )
    
    existing_pair = session.exec(
        select(pair).where(
            ((pair.user_a_name == user_a_username) & (pair.user_b_name == user_b_username)) |
            ((pair.user_a_name == user_b_username) & (pair.user_b_name == user_a_username))

        )
    ).first()
    
    if existing_pair:
        raise HTTPException(status_code = 409, detail = "Pair already exists")
    
    new_pair = pair(
        user_a_name= user_a_username,
        user_b_name=user_b_username,
        created_pair_at = datetime.utcnow()
    )
    
    session.add(new_pair)
    session.commit()
    session.refresh(new_pair)
    
    return{"message" : "Pair created sucessfully", "pair_id": new_pair.pair_id}
    
@app.post("/submit_entry")
def submit_entry(pair_id: int, username: str, entry: str, session: SessionDep):
    # Fetch the user
    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    pair_obj = session.exec(select(pair).where(pair.pair_id == pair_id)).first()
    if not pair_obj:
        raise HTTPException(status_code=404, detail="Pair not found")

    if username != pair_obj.user_a_name and username != pair_obj.user_b_name:
        raise HTTPException(status_code=403, detail="You are not a member of this pair")

    today = date.today()
    note_obj = session.exec(
        select(note).where((note.pair_id == pair_id) & (note.date == today))
    ).first()

    if not note_obj:
        note_obj = note(
            pair_id=pair_id,
            date=today
        )
        session.add(note_obj)

# Assign user-specific entry and ID
    if username == pair_obj.user_a_name:
        note_obj.user_a_entry = entry
        note_obj.user_a_id = user.user_id
        note_obj.user_a_updated = datetime.utcnow()
    elif username == pair_obj.user_b_name:
        note_obj.user_b_entry = entry
        note_obj.user_b_id = user.user_id
        note_obj.user_b_updated = datetime.utcnow()


    session.commit()
    session.refresh(note_obj)


    return {"message": "Entry submitted successfully", "note_id": note_obj.note_id}

@app.put("/add_note_entry")
def add_note_entry(username: str, pair_id: int, date: date, entry: str, session: SessionDep):
    # Fetch the user
    user = session.exec(select(User).where(User.username == username)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Fetch the pair
    pair_obj = session.exec(select(pair).where(pair.pair_id == pair_id)).first()
    if not pair_obj:
        raise HTTPException(status_code=404, detail="Pair does not exist")

    # Confirm the user is part of the pair
    if username != pair_obj.user_a_name and username != pair_obj.user_b_name:
        raise HTTPException(status_code=403, detail="User is not part of the pair")

    # Fetch the note for the given pair and date
    note_obj = session.exec(
        select(note).where((note.pair_id == pair_id) & (note.date == date))
    ).first()
    if not note_obj:
        raise HTTPException(status_code=404, detail="Note for the given pair and date not found")

    # Overwrite the entry based on which user is making the update
    if username == pair_obj.user_a_name:
        note_obj.user_a_entry = entry
        note_obj.user_a_updated = datetime.utcnow()
    elif username == pair_obj.user_b_name:
        note_obj.user_b_entry = entry
        note_obj.user_b_updated = datetime.utcnow()

    session.add(note_obj)
    session.commit()
    session.refresh(note_obj)

    return {"message": "Note entry updated successfully", "note_id": note_obj.note_id}


def delete_user(user_id: int, session: Session = Depends(get_session)):
    user = session.exec(select(User).where(User.user_id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    session.delete(user)
    session.commit()
    return {"message": "User deleted successfully"}


@app.delete("/users/{user_id}")
def api_delete_user(user_id: int, session: Session = Depends(get_session)):
    return delete_user(user_id, session)