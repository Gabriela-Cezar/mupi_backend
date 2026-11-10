from sqlalchemy import Column, Integer, String, Text

from app.database.database import Base


class Theme(Base):
    __tablename__ = "themes"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), unique=True, nullable=False)

    description = Column(Text, nullable=True)