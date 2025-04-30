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
    username : str
    email: str = Field(nullable=False, unique=True, index=True)
    password_hash : str
    created_at: datetime
    
class pair(SQLModel, table = True):
    pair_id:int = Field(default=None, primary_key=True)
    user_a_id : int
    user_b_id : int
    created_pair_at : datetime

class note(SQLModel, table = True):
    note_id: int = Field(default=None, primary_key=True)
    pair_id: int = Field(foreign_key="pair.pair_id")
    date: date
    user_a_id : int
    user_b_id : int
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
    