from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.model.theme import Theme

router = APIRouter(
    prefix="/admin/themes",
    tags=["Administração"]
)

templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates"
)


@router.get("")
def list_themes(db: Session = Depends(get_db)):
    themes = db.query(Theme).order_by(Theme.name).all()

    return [
        {"id": t.id, "name": t.name, "description": t.description}
        for t in themes
    ]


@router.get("/new")
def theme_form(
    request: Request,
    db: Session = Depends(get_db)
):
    themes = db.query(Theme).order_by(Theme.name).all()

    return templates.TemplateResponse(
        request=request,
        name="admin/theme_form.html",
        context={"themes": themes}
    )


@router.post("")
def create_theme(
    name: str = Form(..., min_length=1, max_length=100),
    description: str = Form(None),
    db: Session = Depends(get_db)
):
    name = name.strip()
    description = (description or "").strip() or None

    if not name:
        raise HTTPException(
            status_code=400,
            detail="Informe o nome do tema."
        )

    duplicate = HTTPException(
        status_code=400,
        detail="Já existe um tema com esse nome."
    )

    # "Arte Deco" e "arte deco" são o mesmo tema
    exists = (
        db.query(Theme.id)
        .filter(func.lower(Theme.name) == name.lower())
        .first()
    )

    if exists:
        raise duplicate

    theme = Theme(name=name, description=description)

    db.add(theme)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise duplicate

    db.refresh(theme)

    return {"message": "Tema cadastrado com sucesso!", "id": theme.id}
