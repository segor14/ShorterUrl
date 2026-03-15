import random
import string
from locust import HttpUser, task, between

class ShortenUser(HttpUser):
    wait_time = between(0.1, 0.5)
    token = None
    short_codes = []

    def on_start(self):
        username = f"user_{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}"
        password = "password123"
        
        self.client.post("/auth/register", json={"username": username, "password": password})
        
        # Логин
        response = self.client.post("/auth/login", data={"username": username, "password": password})
        if response.status_code == 200:
            self.token = response.json().get("access_token")
        else:
            print(f"Failed to login: {response.text}")

    @task(5)
    def shorten_link(self):
        if not self.token:
            return
            
        # Генерируем уникальный URL, чтобы избежать ограничений на дубликаты
        random_suffix = "".join(random.choices(string.ascii_letters + string.digits, k=10))
        original_url = f"https://example.com/{random_suffix}"
        
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {"url": original_url}
        
        with self.client.post("/links/shorten", json=payload, headers=headers, name="/links/shorten", catch_response=True) as response:
            if response.status_code == 200:
                response.success()
                data = response.json()
                if "short_code" in data:
                    self.short_codes.append(data["short_code"])
                    if len(self.short_codes) > 100:
                        self.short_codes.pop(0)
            else:
                response.failure(f"Failed to shorten: {response.status_code} - {response.text}")

    @task(10)
    def redirect_link(self):
        if not self.short_codes:
            return
        
        short_code = random.choice(self.short_codes)
        # Мы не хотим следовать редиректу в нагрузочном тесте, так как это тест внешнего ресурса
        self.client.get(f"/links/{short_code}", name="/links/{short_code}", allow_redirects=False)

    @task(2)
    def get_stats(self):
        if not self.short_codes:
            return
        
        short_code = random.choice(self.short_codes)
        self.client.get(f"/links/{short_code}/stats", name="/links/{short_code}/stats")

    @task(1)
    def get_user_me(self):
        if not self.token:
            return
        headers = {"Authorization": f"Bearer {self.token}"}
        self.client.get("/users/me", headers=headers, name="/users/me")
