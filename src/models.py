from datetime import datetime

from pydantic import BaseModel, HttpUrl, Field


class User(BaseModel):
    id: int
    created_at: datetime
    username: str

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str


class CreateShortUrl(BaseModel):
    url: HttpUrl
    expires_at: datetime | None = None
    custom_alias: str | None = Field(None, max_length=50)


class UpdateShortUrl(BaseModel):
    url: HttpUrl | None = None
    expires_at: datetime | None = None
    custom_alias: str | None = Field(None, max_length=50)


class LinkStats(BaseModel):
    original_url: str
    created_at: datetime
    redirects_count: int
    deadline_at: datetime | None

    class Config:
        from_attributes = True


class ShortUrl(BaseModel):
    id: int
    original_url: str
    short_code: str
    redirects_count: int
    deadline_at: datetime | None
    created_at: datetime
    owner_id: int

    class Config:
        from_attributes = True



