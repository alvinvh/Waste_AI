from sqlalchemy import Boolean, Column, Integer, String, Date
from database import Base

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password = Column(String(255), nullable=False)

class Image(Base):
    __tablename__ = 'posts'

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    user_id = Column(Integer, nullable=False)
    result = Column(String(255), nullable=False)
    date = Column(Date, nullable=False)

class Achievement(Base):
    __tablename__ = 'achievement'

    id = Column(Integer, primary_key=True, index=True)
    plastic = Column(Integer, nullable=False)
    paper = Column(Integer, nullable=False)
    cardboard = Column(Integer, nullable=False)
    metal = Column(Integer, nullable=False)
    glass = Column(Integer, nullable=False)
    total = Column(Integer, nullable=False)
