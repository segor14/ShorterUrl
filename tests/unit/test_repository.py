import pytest
from datetime import datetime, timedelta, timezone
from src.db.repository import UserRepository, LinkRepository
from src.db.exceptions import (
    UserAlreadyExistsException,
    UserNotFound,
    LinkNotFound,
    LinkAlreadyExists,
)
from src.models import User as UserSchema, ShortUrl as ShortUrlSchema


@pytest.mark.anyio
class TestUserRepository:
    async def test_create_user_success(self, session):
        repo = UserRepository(session)
        username = "testuser"
        password = "testpassword"

        user = await repo.create_user(username, password)

        assert user.username == username
        assert user.id is not None

    async def test_create_user_duplicate(self, session):
        repo = UserRepository(session)
        username = "duplicate_user"
        password = "password"

        await repo.create_user(username, password)

        with pytest.raises(UserAlreadyExistsException):
            async with session.begin_nested():
                await repo.create_user(username, password)

    async def test_get_user_success(self, session):
        repo = UserRepository(session)
        username = "getuser"
        password = "secure_password"

        await repo.create_user(username, password)

        user = await repo.get_user(username, password)
        assert user.username == username

    async def test_get_user_wrong_password(self, session):
        repo = UserRepository(session)
        username = "wrongpass_user"
        password = "correct_password"

        await repo.create_user(username, password)

        with pytest.raises(UserNotFound):
            await repo.get_user(username, "wrong_password")

    async def test_get_user_not_found(self, session):
        repo = UserRepository(session)
        with pytest.raises(UserNotFound):
            await repo.get_user("nonexistent", "any")

    async def test_get_user_by_id(self, session):
        repo = UserRepository(session)
        created_user = await repo.create_user("by_id", "pass")

        user = await repo.get_user_by_id(created_user.id)
        assert user.username == "by_id"

    async def test_get_user_by_username(self, session):
        repo = UserRepository(session)
        await repo.create_user("by_username", "pass")

        user = await repo.get_user_by_username("by_username")
        assert user.username == "by_username"


@pytest.mark.anyio
class TestLinkRepository:
    async def test_create_short_url_success(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("link_user", "pass")

        link_repo = LinkRepository(session)
        original_url = "https://example.com"

        short_url = await link_repo.create_short_url(original_url, user.id)

        assert short_url.original_url == original_url
        assert len(short_url.short_code) == 6
        assert short_url.owner_id == user.id

    async def test_create_short_url_custom_code(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("custom_link_user", "pass")

        link_repo = LinkRepository(session)
        original_url = "https://example.org"
        custom_code = "my-custom-code"

        short_url = await link_repo.create_short_url(
            original_url, user.id, short_code=custom_code
        )

        assert short_url.short_code == custom_code

    async def test_get_url_by_code_success(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("get_link_user", "pass")

        link_repo = LinkRepository(session)
        created = await link_repo.create_short_url("https://test.com", user.id)

        found = await link_repo.get_url_by_code(created.short_code)
        assert found.original_url == "https://test.com"

    async def test_get_url_by_code_expired(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("expired_link_user", "pass")

        link_repo = LinkRepository(session)
        past_deadline = datetime.now(timezone.utc) - timedelta(days=1)
        created = await link_repo.create_short_url(
            "https://expired.com", user.id, deadline_at=past_deadline
        )

        with pytest.raises(LinkNotFound):
            await link_repo.get_url_by_code(created.short_code)

    async def test_increment_redirect_count(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("inc_user", "pass")

        link_repo = LinkRepository(session)
        created = await link_repo.create_short_url("https://inc.com", user.id)

        await link_repo.increment_redirect_count(created.short_code)

        found = await link_repo.get_url_by_code(created.short_code)
        assert found.redirects_count == 1

    async def test_delete_link(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("del_user", "pass")

        link_repo = LinkRepository(session)
        created = await link_repo.create_short_url("https://del.com", user.id)

        await link_repo.delete_link(created.short_code, user.id)

        with pytest.raises(LinkNotFound):
            await link_repo.get_url_by_code(created.short_code)

    async def test_delete_link_wrong_owner(self, session):
        user_repo = UserRepository(session)
        user1 = await user_repo.create_user("owner1", "pass")
        user2 = await user_repo.create_user("owner2", "pass")

        link_repo = LinkRepository(session)
        created = await link_repo.create_short_url("https://wrong-owner.com", user1.id)

        with pytest.raises(LinkNotFound):
            await link_repo.delete_link(created.short_code, user2.id)

    async def test_get_user_by_id_not_found(self, session):
        repo = UserRepository(session)
        with pytest.raises(UserNotFound):
            await repo.get_user_by_id(9999)

    async def test_get_user_by_username_not_found(self, session):
        repo = UserRepository(session)
        with pytest.raises(UserNotFound):
            await repo.get_user_by_username("nonexistent")

    async def test_create_short_url_collision_retry(self, session, mocker):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("collision_user", "pass")
        link_repo = LinkRepository(session)

        mocker.patch.object(
            link_repo,
            "_generate_short_code",
            side_effect=["code1", "code1", "code2"]
        )

        await link_repo.create_short_url("https://url1.com", user.id)
        res = await link_repo.create_short_url("https://url2.com", user.id)
        assert res.short_code == "code2"

    async def test_create_short_url_duplicate_url(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("dup_url_user", "pass")
        link_repo = LinkRepository(session)

        await link_repo.create_short_url("https://same.com", user.id)
        with pytest.raises(LinkAlreadyExists, match="URL already exists"):
            async with session.begin_nested():
                await link_repo.create_short_url("https://same.com", user.id)

    async def test_get_link_by_original_url_success(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("orig_user", "pass")
        link_repo = LinkRepository(session)
        await link_repo.create_short_url("https://orig.com", user.id)

        found = await link_repo.get_link_by_original_url("https://orig.com")
        assert found.original_url == "https://orig.com"

    async def test_get_link_by_original_url_not_found(self, session):
        link_repo = LinkRepository(session)
        with pytest.raises(LinkNotFound):
            await link_repo.get_link_by_original_url("https://notfound.com")

    async def test_get_link_by_original_url_expired(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("orig_exp_user", "pass")
        link_repo = LinkRepository(session)
        past_deadline = datetime.now(timezone.utc) - timedelta(days=1)
        await link_repo.create_short_url("https://orig-exp.com", user.id, deadline_at=past_deadline)

        with pytest.raises(LinkNotFound):
            await link_repo.get_link_by_original_url("https://orig-exp.com")

    async def test_update_link_success(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("upd_user", "pass")
        link_repo = LinkRepository(session)
        created = await link_repo.create_short_url("https://old.com", user.id)

        updated = await link_repo.update_link(
            created.short_code, user.id, new_url="https://new.com"
        )
        assert updated.original_url == "https://new.com"

    async def test_update_link_no_changes(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("upd_none_user", "pass")
        link_repo = LinkRepository(session)
        created = await link_repo.create_short_url("https://none.com", user.id)

        updated = await link_repo.update_link(created.short_code, user.id)
        assert updated.original_url == "https://none.com"

    async def test_update_link_not_found(self, session):
        link_repo = LinkRepository(session)
        with pytest.raises(LinkNotFound):
            await link_repo.update_link("nocode", 1, new_url="https://new.com")

    async def test_update_link_duplicate_short_code(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("upd_dup_user", "pass")
        link_repo = LinkRepository(session)
        await link_repo.create_short_url("https://10.com", user.id, short_code="code10")
        await link_repo.create_short_url("https://20.com", user.id, short_code="code20")

        with pytest.raises(LinkAlreadyExists):
            async with session.begin_nested():
                await link_repo.update_link("code10", user.id, new_short_code="code20")

    async def test_create_short_url_custom_code_collision(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("custom_coll_user", "pass")
        link_repo = LinkRepository(session)
        await link_repo.create_short_url("https://url40.com", user.id, short_code="manual")

        with pytest.raises(LinkAlreadyExists):
            async with session.begin_nested():
                await link_repo.create_short_url("https://url50.com", user.id, short_code="manual")

    async def test_create_short_url_max_retries_fail(self, session, mocker):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("retry_fail_user", "pass")
        link_repo = LinkRepository(session)
        
        await link_repo.create_short_url("https://existing.com", user.id, short_code="fixed")
        
        mocker.patch.object(link_repo, "_generate_short_code", return_value="fixed")
        
        with pytest.raises(LinkAlreadyExists):
            async with session.begin_nested():
                await link_repo.create_short_url("https://new.com", user.id)

    async def test_update_link_with_deadline(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("upd_deadline_user", "pass")
        link_repo = LinkRepository(session)
        created = await link_repo.create_short_url("https://deadline.com", user.id)
        
        new_deadline = datetime.now(timezone.utc) + timedelta(days=5)
        updated = await link_repo.update_link(created.short_code, user.id, deadline_at=new_deadline)
        
        assert abs((updated.deadline_at - new_deadline).total_seconds()) < 1

    async def test_create_short_url_custom_code_collision(self, session):
        user_repo = UserRepository(session)
        user = await user_repo.create_user("custom_coll_user", "pass")
        link_repo = LinkRepository(session)
        await link_repo.create_short_url("https://url12.com", user.id, short_code="manual")
        
        with pytest.raises(LinkAlreadyExists, match="Short code already exists"):
            async with session.begin_nested():
                await link_repo.create_short_url("https://url22.com", user.id, short_code="manual")
        await session.rollback()
