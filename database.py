import os
from sqlmodel import SQLModel, create_engine
from models import *

engine = create_engine('sqlite:///database.db')

def create_db():
    SQLModel.metadata.create_all(engine)