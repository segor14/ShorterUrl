from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import FastAPI, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt

from src.db.db import get_db, engine
from src.db.repository import UserRepository, LinkRepository
from src.db.exceptions import UserAlreadyExistsException, UserNotFound, LinkNotFound, LinkAlreadyExists
from src.models import User, UserCreate, Token, ShortUrl, CreateShortUrl, LinkStats, UpdateShortUrl
from src.settings import settings
from src.db.models import Base


app = FastAPI()


@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    repo = UserRepository(db)
    try:
        user = await repo.get_user_by_username(username)
        return user
    except UserNotFound:
        raise credentials_exception


@app.post("/auth/register", response_model=User)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    try:
        user = await repo.create_user(user_data.username, user_data.password)
        return user
    except UserAlreadyExistsException:
        raise HTTPException(status_code=400, detail="User already exists")


@app.post("/auth/login", response_model=Token)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: AsyncSession = Depends(get_db)
):
    repo = UserRepository(db)
    try:
        user = await repo.get_user(form_data.username, form_data.password)
        access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
        access_token = create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        return {"access_token": access_token, "token_type": "bearer"}
    except UserNotFound:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/users/me", response_model=User)
async def read_users_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user


@app.post("/links/shorten", response_model=ShortUrl)
async def shorten_link(
    data: CreateShortUrl,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    repo = LinkRepository(db)
    try:
        link = await repo.create_short_url(
            original_url=str(data.url),
            owner_id=current_user.id,
            short_code=data.custom_alias,
            deadline_at=data.expires_at
        )
        return link
    except LinkAlreadyExists as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/links/search", response_model=ShortUrl)
async def search_link(
    original_url: str,
    db: AsyncSession = Depends(get_db)
):
    repo = LinkRepository(db)
    try:
        link = await repo.get_link_by_original_url(original_url)
        return link
    except LinkNotFound:
        raise HTTPException(status_code=404, detail="Link not found")


@app.get("/links/{short_code}")
async def redirect_to_url(
    short_code: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    repo = LinkRepository(db)
    try:
        link = await repo.get_url_by_code(short_code)
        background_tasks.add_task(repo.increment_redirect_count, short_code)
        
        response = RedirectResponse(url=link.original_url)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
    except LinkNotFound:
        raise HTTPException(status_code=404, detail="Link not found or expired")


@app.get("/links/{short_code}/stats", response_model=LinkStats)
async def get_link_stats(
    short_code: str,
    db: AsyncSession = Depends(get_db)
):
    repo = LinkRepository(db)
    try:
        link = await repo.get_url_by_code(short_code)
        return link
    except LinkNotFound:
        raise HTTPException(status_code=404, detail="Link not found or expired")


@app.delete("/links/{short_code}")
async def delete_link(
    short_code: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    repo = LinkRepository(db)
    try:
        await repo.delete_link(short_code, current_user.id)
        return {"detail": "Link deleted"}
    except LinkNotFound:
        raise HTTPException(status_code=404, detail="Link not found or not owned by user")


@app.put("/links/{short_code}", response_model=ShortUrl)
async def update_link(
    short_code: str,
    data: UpdateShortUrl,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    repo = LinkRepository(db)
    try:
        link = await repo.update_link(
            short_code=short_code,
            owner_id=current_user.id,
            new_url=str(data.url) if data.url else None,
            deadline_at=data.expires_at,
            new_short_code=data.custom_alias
        )
        return link
    except LinkNotFound:
        raise HTTPException(status_code=404, detail="Link not found or not owned by user")
    except LinkAlreadyExists as e:
        raise HTTPException(status_code=400, detail=str(e))
