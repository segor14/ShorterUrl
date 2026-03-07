from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models import User as UserSchema, ShortUrl as ShortUrlSchema
from src.db.models import User as UserModel, ShortUrl as ShortUrlModel
from src.db.exceptions import UserAlreadyExistsException, UserNotFound, LinkNotFound, LinkAlreadyExists
from logging import getLogger
from sqlalchemy.exc import IntegrityError
import string
import random
from datetime import datetime, timedelta, timezone

logger = getLogger(__name__)


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user(self, username: str, password: str) -> UserSchema:
        logger.debug(f"Get user {username}")
        # Использование crypt из pgcrypto в SQLAlchemy для проверки пароля
        # Предполагаем, что pgcrypto уже включен в БД
        query = select(UserModel).where(
            UserModel.username == username,
            UserModel.password_hash == func.crypt(password, UserModel.password_hash)
        )
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFound()
        return UserSchema.model_validate(user)

    async def create_user(self, username: str, password: str) -> UserSchema:
        logger.debug(f"Create user {username}")
        # Генерация соли и хеша через crypt на стороне БД
        user = UserModel(
            username=username,
            password_hash=func.crypt(password, func.gen_salt('bf'))
        )
        self.session.add(user)
        try:
            await self.session.commit()
            await self.session.refresh(user)
            return UserSchema.model_validate(user)
        except IntegrityError:
            await self.session.rollback()
            raise UserAlreadyExistsException()

    async def get_user_by_id(self, user_id: int) -> UserSchema:
        query = select(UserModel).where(UserModel.id == user_id)
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFound()
        return UserSchema.model_validate(user)

    async def get_user_by_username(self, username: str) -> UserSchema:
        query = select(UserModel).where(UserModel.username == username)
        result = await self.session.execute(query)
        user = result.scalar_one_or_none()
        if not user:
            raise UserNotFound()
        return UserSchema.model_validate(user)


class LinkRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_short_url(
        self,
        original_url: str,
        owner_id: int,
        short_code: str | None = None,
        deadline_at: datetime | None = None
    ) -> ShortUrlSchema:
        if not deadline_at:
            deadline_at = datetime.now(timezone.utc) + timedelta(days=30)

        if deadline_at.tzinfo is None:
            deadline_at = deadline_at.replace(tzinfo=timezone.utc)

        max_retries = 10
        for _ in range(max_retries):
            current_code = short_code or self._generate_short_code()
            link = ShortUrlModel(
                original_url=original_url,
                short_code=current_code,
                owner_id=owner_id,
                deadline_at=deadline_at
            )
            self.session.add(link)
            try:
                await self.session.commit()
                await self.session.refresh(link)
                return ShortUrlSchema.model_validate(link)

            except IntegrityError as e:
                await self.session.rollback()
                error_msg = str(e.orig).lower()
                if "url_unique_constraint" in error_msg or "original_url" in error_msg:
                    raise LinkAlreadyExists("Link with this URL already exists")

                if short_code:
                    raise LinkAlreadyExists("Short code already exists")
                continue

        raise LinkAlreadyExists()

    def _generate_short_code(self, length: int = 6) -> str:
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))

    async def get_url_by_code(self, short_code: str) -> ShortUrlModel:

        query = select(ShortUrlModel).where(ShortUrlModel.short_code == short_code)
        result = await self.session.execute(query)
        link = result.scalar_one_or_none()
        if not link:
            raise LinkNotFound()
        
        if link.deadline_at:
            deadline = link.deadline_at
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)

            if deadline < datetime.now(timezone.utc):
                await self.session.delete(link)
                await self.session.commit()
                raise LinkNotFound()
            
        return link

    async def get_link_by_original_url(self, original_url: str) -> ShortUrlSchema:
        query = select(ShortUrlModel).where(ShortUrlModel.original_url == original_url)
        result = await self.session.execute(query)
        link = result.scalar_one_or_none()
        if not link:
            raise LinkNotFound()
        
        if link.deadline_at:
            deadline = link.deadline_at
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            
            if deadline < datetime.now(timezone.utc):
                await self.session.delete(link)
                await self.session.commit()
                raise LinkNotFound()

        return ShortUrlSchema.model_validate(link)

    async def increment_redirect_count(self, short_code: str):
        query = update(ShortUrlModel).where(
            ShortUrlModel.short_code == short_code
        ).values(redirects_count=ShortUrlModel.redirects_count + 1)
        await self.session.execute(query)
        await self.session.commit()

    async def delete_link(self, short_code: str, owner_id: int):
        query = delete(ShortUrlModel).where(
            ShortUrlModel.short_code == short_code,
            ShortUrlModel.owner_id == owner_id
        )
        result = await self.session.execute(query)
        if result.rowcount == 0:
            raise LinkNotFound()
        await self.session.commit()

    async def update_link(
        self, 
        short_code: str, 
        owner_id: int, 
        new_url: str | None = None, 
        deadline_at: datetime | None = None,
        new_short_code: str | None = None
    ) -> ShortUrlSchema:
        logger.debug(f"Updating link {short_code} for owner {owner_id}")
        values = {}
        if new_url is not None:
            values["original_url"] = new_url
        if deadline_at is not None:
            if deadline_at.tzinfo is None:
                deadline_at = deadline_at.replace(tzinfo=timezone.utc)
            values["deadline_at"] = deadline_at
        if new_short_code is not None:
            values["short_code"] = new_short_code

        if not values:
            logger.debug("No values to update")
            query = select(ShortUrlModel).where(
                ShortUrlModel.short_code == short_code,
                ShortUrlModel.owner_id == owner_id
            )
            result = await self.session.execute(query)
            link = result.scalar_one_or_none()
            if not link:
                raise LinkNotFound()
            return ShortUrlSchema.model_validate(link)

        query = update(ShortUrlModel).where(
            ShortUrlModel.short_code == short_code,
            ShortUrlModel.owner_id == owner_id
        ).values(**values).returning(ShortUrlModel)
        
        try:
            result = await self.session.execute(query)
            link = result.scalar_one_or_none()
            if not link:
                await self.session.rollback()
                raise LinkNotFound()
            
            await self.session.commit()

            return ShortUrlSchema.model_validate(link)
        except IntegrityError as e:
            await self.session.rollback()
            error_msg = str(e.orig).lower()
            if "url_unique_constraint" in error_msg or "original_url" in error_msg:
                raise LinkAlreadyExists("Link with this URL already exists")
            raise LinkAlreadyExists()
