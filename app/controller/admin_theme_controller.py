from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.model.theme import Theme

router = APIRouter(
    prefix="/admin/themes",
    tags=["Administração"]
)


@router.get("")
def list_themes(db: Session = Depends(get_db)):
    themes = db.query(Theme).order_by(Theme.name).all()

    return [
        {"id": t.id, "name": t.name, "description": t.description}
        for t in themes
    ]


@router.post("")
def create_theme(
    name: str = Form(..., min_length=1, max_length=100),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    theme = Theme(name=name.strip(), description=description)

    db.add(theme)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail="Já existe um tema com esse nome."
        )

    db.refresh(theme)

    return {"message": "Tema cadastrado com sucesso!", "id": theme.id}