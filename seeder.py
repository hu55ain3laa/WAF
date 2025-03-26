from sqlmodel import Session
from database import engine
from models import *
def seed():
    with Session(engine) as session:
        lis = [SubType(name='ECO'), SubType(name='ECO+'), SubType(name='STD'), SubType(name='TUR'), SubType(name='GAM'), SubType(name='A3MALI')]
        for i in lis:
            session.add(i)
        session.commit()