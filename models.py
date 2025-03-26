from sqlmodel import Field, SQLModel, Relationship
from typing import List, Optional

class User(SQLModel, table = True):
    id : int = Field(primary_key=True)
    username : str = Field(unique=True)
    name : str
    phone : str
    notes : str

    # Relationships
    ips: List["Ips"] = Relationship(back_populates="user")
    subscriptions: List["Subscriptions"] = Relationship(back_populates="user")

class Ips(SQLModel, table = True):
    id : int = Field(primary_key=True)
    ip : str
    name: str
    user_id : int = Field(foreign_key='user.id')

    # Relationships
    user: User = Relationship(back_populates="ips")

class SubType(SQLModel, table = True):
    id : int = Field(primary_key=True)
    name : str = Field(unique=True)

    # Relationships
    subscriptions: List["Subscriptions"] = Relationship(back_populates="sub_type")

class Subscriptions(SQLModel, table = True):
    id : int = Field(primary_key=True)
    user_id : int = Field(foreign_key='user.id')
    users_count : int
    discount : int
    sub_type_id : int = Field(foreign_key='subtype.id')
    notes : str

    # Relationships
    user: User = Relationship(back_populates="subscriptions")
    sub_type: SubType = Relationship(back_populates="subscriptions")