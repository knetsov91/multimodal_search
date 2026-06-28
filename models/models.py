from db.database import Base
from sqlalchemy import Column, Integer, String, LargeBinary, Text

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(30), index=True, unique=True)
    role = Column(String(30), index=True)
    password = Column(LargeBinary)

class Recipe(Base):
    __tablename__ = "recipes"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(100), index=True)
    text = Column(Text)
    img_name = Column(String(256))