from db.database import Base
from sqlalchemy import Column, Integer, String, LargeBinary
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(30), index=True, unique=True)
    role = Column(String(30), index=True)
    password = Column(LargeBinary)