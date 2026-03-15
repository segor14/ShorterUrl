import pytest
from datetime import datetime, timedelta, timezone

@pytest.mark.anyio
class TestFunctionalAPI:
    async def test_full_link_lifecycle(self, client):
        # 1. Регистрация
        username = "api_user"
        password = "api_password"
        resp = await client.post("/auth/register", json={"username": username, "password": password})
        assert resp.status_code == 200
        
        # 2. Логин
        resp = await client.post("/auth/login", data={"username": username, "password": password})
        assert resp.status_code == 200
        token = resp.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 3. Создание короткой ссылки
        original_url = "https://www.google.com/"
        resp = await client.post(
            "/links/shorten", 
            json={"url": original_url, "custom_alias": "google"},
            headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["original_url"] == original_url
        assert data["short_code"] == "google"
        
        # 4. Проверка перенаправления
        resp = await client.get("/links/google")
        assert resp.status_code == 307
        assert resp.headers["location"] == original_url

        # 5. Проверка статистики
        resp = await client.get("/links/google/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["original_url"] == original_url
        
        # 6. Обновление ссылки
        new_url = "https://www.bing.com/"
        resp = await client.put(
            "/links/google",
            json={"url": new_url},
            headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["original_url"] == new_url

        # 7. Поиск ссылки
        resp = await client.get(f"/links/search?original_url={new_url}")
        assert resp.status_code == 200
        assert resp.json()["short_code"] == "google"

        # 8. Удаление ссылки
        resp = await client.delete("/links/google", headers=auth_headers)
        assert resp.status_code == 200
        
        # 9. Проверка удаления
        resp = await client.get("/links/google")
        assert resp.status_code == 404

    async def test_invalid_data(self, client):
        # Регистрация для получения токена
        await client.post("/auth/register", json={"username": "invalid_test", "password": "pass"})
        resp = await client.post("/auth/login", data={"username": "invalid_test", "password": "pass"})
        token = resp.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # Невалидный URL
        resp = await client.post(
            "/links/shorten", 
            json={"url": "not-a-url"},
            headers=auth_headers
        )
        assert resp.status_code == 422

        # Дубликат кастомного алиаса
        await client.post(
            "/links/shorten", 
            json={"url": "https://url1.com", "custom_alias": "dup"},
            headers=auth_headers
        )
        resp = await client.post(
            "/links/shorten", 
            json={"url": "https://url2.com", "custom_alias": "dup"},
            headers=auth_headers
        )
        assert resp.status_code == 400
        assert "exists" in resp.json()["detail"].lower()

    async def test_expired_link(self, client, session):
        # Создаем пользователя вручную через репозиторий для скорости или через API
        await client.post("/auth/register", json={"username": "expired_user", "password": "pass"})
        resp = await client.post("/auth/login", data={"username": "expired_user", "password": "pass"})
        token = resp.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # Создаем ссылку с истекшим сроком
        past_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        resp = await client.post(
            "/links/shorten", 
            json={"url": "https://expired.com", "custom_alias": "old", "expires_at": past_time},
            headers=auth_headers
        )
        assert resp.status_code == 200
        
        resp = await client.get("/links/old")
        assert resp.status_code == 404

    async def test_unauthorized_access(self, client):
        # Попытка создания без токена
        resp = await client.post("/links/shorten", json={"url": "https://example.com"})
        assert resp.status_code == 401

    async def test_delete_other_user_link(self, client):
        # Регистрируем двух пользователей
        await client.post("/auth/register", json={"username": "user1", "password": "pass"})
        await client.post("/auth/register", json={"username": "user2", "password": "pass"})
        
        # User 1 создает ссылку
        resp = await client.post("/auth/login", data={"username": "user1", "password": "pass"})
        token1 = resp.json()["access_token"]
        await client.post(
            "/links/shorten", 
            json={"url": "https://user1.com", "custom_alias": "u1link"},
            headers={"Authorization": f"Bearer {token1}"}
        )

        # User 2 пытается удалить ссылку User 1
        resp = await client.post("/auth/login", data={"username": "user2", "password": "pass"})
        token2 = resp.json()["access_token"]
        resp = await client.delete(
            "/links/u1link", 
            headers={"Authorization": f"Bearer {token2}"}
        )
        assert resp.status_code == 404
        assert "not owned" in resp.json()["detail"].lower()

    async def test_register_duplicate(self, client):
        await client.post("/auth/register", json={"username": "dup_reg", "password": "pass"})
        resp = await client.post("/auth/register", json={"username": "dup_reg", "password": "pass"})
        assert resp.status_code == 400
        assert "already exists" in resp.json()["detail"].lower()

    async def test_login_invalid(self, client):
        resp = await client.post("/auth/login", data={"username": "nonexistent", "password": "any"})
        assert resp.status_code == 401

    async def test_get_me_unauthorized(self, client):
        resp = await client.get("/users/me")
        assert resp.status_code == 401

    async def test_search_not_found(self, client):
        resp = await client.get("/links/search?original_url=https://notfound.com")
        assert resp.status_code == 404

    async def test_stats_not_found(self, client):
        resp = await client.get("/links/nonexistent/stats")
        assert resp.status_code == 404

    async def test_update_not_found(self, client):
        await client.post("/auth/register", json={"username": "upd_err", "password": "pass"})
        resp = await client.post("/auth/login", data={"username": "upd_err", "password": "pass"})
        token = resp.json()["access_token"]
        resp = await client.put(
            "/links/nonexistent", 
            json={"url": "https://new.com"},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 404

    async def test_invalid_token(self, client):
        resp = await client.get("/users/me", headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code == 401

    async def test_token_no_sub(self, client):
        from src.app import create_access_token
        token = create_access_token(data={"some": "other"}, expires_delta=None)
        resp = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    async def test_token_user_not_found(self, client):
        from src.app import create_access_token
        token = create_access_token(data={"sub": "ghost_user"})
        resp = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    async def test_startup_event(self):
        from src.app import startup
        await startup()

    async def test_read_users_me_success(self, client):
        await client.post("/auth/register", json={"username": "me_user", "password": "pass"})
        resp = await client.post("/auth/login", data={"username": "me_user", "password": "pass"})
        token = resp.json()["access_token"]
        resp = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["username"] == "me_user"

    async def test_update_link_collision(self, client):
        await client.post("/auth/register", json={"username": "coll_user", "password": "pass"})
        resp = await client.post("/auth/login", data={"username": "coll_user", "password": "pass"})
        token = resp.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        await client.post("/links/shorten", json={"url": "https://url1.com", "custom_alias": "c1"}, headers=auth_headers)
        await client.post("/links/shorten", json={"url": "https://url2.com", "custom_alias": "c2"}, headers=auth_headers)

        resp = await client.put("/links/c1", json={"custom_alias": "c2"}, headers=auth_headers)
        assert resp.status_code in [400, 404]

    async def test_redirect_headers(self, client):
        await client.post("/auth/register", json={"username": "redir_user", "password": "pass"})
        resp = await client.post("/auth/login", data={"username": "redir_user", "password": "pass"})
        token = resp.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}
        
        await client.post("/links/shorten", json={"url": "https://example.com", "custom_alias": "redir"}, headers=auth_headers)
        
        resp = await client.get("/links/redir")
        assert resp.status_code == 307
        assert resp.headers["Cache-Control"] == "no-cache, no-store, must-revalidate, max-age=0"
        assert resp.headers["Pragma"] == "no-cache"
        assert resp.headers["Expires"] == "0"

    async def test_direct_app_calls(self, session):
        from src.app import register, login, shorten_link, search_link, redirect_to_url, get_link_stats, delete_link, update_link
        from src.models import UserCreate, CreateShortUrl, UpdateShortUrl
        from fastapi import BackgroundTasks
        from fastapi.security import OAuth2PasswordRequestForm
        
        user = await register(UserCreate(username="direct_user", password="pass"), session)
        assert user.username == "direct_user"
        
        form_data = OAuth2PasswordRequestForm(username="direct_user", password="pass")
        token_data = await login(form_data, session)
        assert "access_token" in token_data
        
        link = await shorten_link(CreateShortUrl(url="https://direct.com/"), user, session)
        assert link.original_url == "https://direct.com/"
        
        found = await search_link("https://direct.com/", session)
        assert found.short_code == link.short_code
        
        stats = await get_link_stats(link.short_code, session)
        assert stats.original_url == link.original_url
        
        updated = await update_link(link.short_code, UpdateShortUrl(url="https://direct-updated.com/"), user, session)
        assert updated.original_url == "https://direct-updated.com/"

        bg = BackgroundTasks()
        resp = await redirect_to_url(link.short_code, bg, session)
        assert resp.status_code == 307
        
        resp_del = await delete_link(link.short_code, user, session)
        assert resp_del == {"detail": "Link deleted"}

    async def test_app_exceptions_direct(self, session):
        from src.app import register, login, shorten_link, search_link, redirect_to_url, get_link_stats, delete_link, update_link
        from src.models import UserCreate, CreateShortUrl, UpdateShortUrl
        from fastapi import HTTPException, BackgroundTasks
        from fastapi.security import OAuth2PasswordRequestForm
        from src.db.exceptions import LinkAlreadyExists
        import pytest
        
        await register(UserCreate(username="direct_dup", password="pass"), session)
        with pytest.raises(HTTPException) as exc:
            await register(UserCreate(username="direct_dup", password="pass"), session)
        assert exc.value.status_code == 400
        
        with pytest.raises(HTTPException) as exc:
            await login(OAuth2PasswordRequestForm(username="ghost", password="any"), session)
        assert exc.value.status_code == 401
        
        with pytest.raises(HTTPException) as exc:
            await search_link("https://notfound.com", session)
        assert exc.value.status_code == 404
        
        with pytest.raises(HTTPException) as exc:
            await redirect_to_url("ghostcode", BackgroundTasks(), session)
        assert exc.value.status_code == 404
        
        with pytest.raises(HTTPException) as exc:
            await get_link_stats("ghostcode", session)
        assert exc.value.status_code == 404
        
        user = await register(UserCreate(username="owner_user", password="pass"), session)
        
        with pytest.raises(HTTPException) as exc:
            await delete_link("ghostcode", user, session)
        assert exc.value.status_code == 404
        
        with pytest.raises(HTTPException) as exc:
            await update_link("ghostcode", UpdateShortUrl(url="https://new.com/"), user, session)
        assert exc.value.status_code == 404
        
    async def test_get_current_user_direct(self, session):
        from src.app import get_current_user, create_access_token, register
        from src.models import UserCreate
        from fastapi import HTTPException
        import pytest
        
        user_schema = await register(UserCreate(username="token_user", password="pass"), session)
        token = create_access_token(data={"sub": "token_user"})
        
        current_user = await get_current_user(token, session)
        assert current_user.username == "token_user"
        
        token_ghost = create_access_token(data={"sub": "ghost"})
        with pytest.raises(HTTPException) as exc:
            await get_current_user(token_ghost, session)
        assert exc.value.status_code == 401
        
    async def test_app_collisions_direct(self, session, mocker):
        from src.app import shorten_link, update_link, register
        from src.models import UserCreate, CreateShortUrl, UpdateShortUrl
        from src.db.exceptions import LinkAlreadyExists
        from fastapi import HTTPException
        import pytest
        
        user = await register(UserCreate(username="coll_user_direct", password="pass"), session)
        
        mocker.patch("src.app.LinkRepository.create_short_url", side_effect=LinkAlreadyExists("Collision"))
        with pytest.raises(HTTPException) as exc:
            await shorten_link(CreateShortUrl(url="https://test.com/"), user, session)
        assert exc.value.status_code == 400
        assert "Collision" in exc.value.detail
        
        mocker.patch("src.app.LinkRepository.update_link", side_effect=LinkAlreadyExists("CollisionUpd"))
        with pytest.raises(HTTPException) as exc:
            await update_link("code", UpdateShortUrl(url="https://test.com/"), user, session)
        assert exc.value.status_code == 400
        assert "CollisionUpd" in exc.value.detail
