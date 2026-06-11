from sqlalchemy.orm import Session
from models.models import User
import bcrypt

def register(db: Session, email: str, password: str):

    s = bcrypt.gensalt()
    h = bcrypt.hashpw(password.encode("utf-8"), s)
    try:
        user = User(email=email, password=h, role="user")
        db.add(user)
        db.commit()
        db.refresh(user)
    except Exception as e:
        raise e

def get_user_by_email(db: Session, email: str):
    try:
        return db.query(User).filter(User.email == email).first()
    except Exception as e:
        raise e

