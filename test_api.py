"""독립된 메모리 SQLite로 요청 검증/인증/작성자 권한을 확인. PostgreSQL 검증과 구분."""
import asyncio
import os
import secrets
import unittest
from datetime import UTC, datetime, timedelta
os.environ["BOARD_TESTING"] = "1"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET"] = secrets.token_hex(32)
import jwt
from fastapi.testclient import TestClient
from database import Base, engine
from main import app
from security import SECRET

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app)
        cls.client = cls.context.__enter__()
        async def prepare():
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        cls.client.portal.call(prepare)

    @classmethod
    def tearDownClass(cls):
        cls.client.portal.call(engine.dispose)
        cls.context.__exit__(None, None, None)

    def test_crud_auth_and_ownership(self):
        c = self.client
        tokens = []
        for name in ["author", "other"]:
            data = {"email": name + "@example.test", "password": "test-password-2026"}
            result = c.post("/auth/signup", json=data)
            self.assertEqual(result.status_code, 201, result.text)
            self.assertNotIn("password_hash", result.json())
            login = c.post("/auth/token", data={"username": data["email"], "password": data["password"]})
            self.assertEqual(login.status_code, 200)
            tokens.append({"Authorization": "Bearer " + login.json()["access_token"]})
        author, other = tokens
        payload = {"title": "첫 글", "content": "격리된 테스트 내용"}
        self.assertEqual(c.post("/posts", json=payload).status_code, 401)
        result = c.post("/posts", json=payload, headers=author)
        self.assertEqual(result.status_code, 201, result.text)
        post = result.json()
        url = "/posts/" + str(post["id"])
        self.assertEqual(c.get(url).status_code, 200)
        self.assertEqual(len(c.get("/posts").json()), 1)
        updated = {"title": "수정 글", "content": "수정 내용"}
        for method in ["put", "delete"]:
            result = c.request(method, url, headers=other, **({"json": updated} if method == "put" else {}))
            self.assertEqual(result.status_code, 403)
        self.assertEqual(c.get(url).json()["title"], "첫 글")
        self.assertEqual(c.put(url, json=updated, headers=author).json()["title"], "수정 글")
        self.assertEqual(c.delete(url, headers=author).status_code, 204)
        self.assertEqual(c.get(url).status_code, 404)
        self.assertEqual(c.get("/posts").json(), [])

    def test_validation_and_invalid_tokens(self):
        c = self.client
        self.assertEqual(c.post("/auth/signup", json={"email":"invalid","password":"short"}).status_code, 422)
        self.assertEqual(c.post("/auth/token", data={"username":"missing@example.test","password":"wrong"}).status_code, 401)
        payload = {"title": "글", "content": "내용"}
        for token in ["invalid", jwt.encode({"sub":"1","exp":datetime.now(UTC)-timedelta(minutes=1)}, SECRET, algorithm="HS256")]:
            self.assertEqual(c.post("/posts", json=payload, headers={"Authorization": "Bearer "+token}).status_code, 401)
        self.assertEqual(c.get("/posts/0").status_code, 422)
        self.assertEqual(c.get("/posts?limit=999").status_code, 422)
        self.assertEqual(c.get("/docs").status_code, 200)
        schema = c.get("/openapi.json").json()
        self.assertIn("/posts/{post_id}", schema["paths"])

    def test_request_cannot_choose_author(self):
        c = self.client
        data={"email":"validation@example.test","password":"test-password-2026"}
        self.assertEqual(c.post("/auth/signup", json=data).status_code,201)
        self.assertEqual(c.post("/auth/signup", json=data).status_code,409)
        token=c.post("/auth/token",data={"username":data["email"],"password":data["password"]}).json()["access_token"]
        headers={"Authorization":"Bearer "+token}
        for body in [{"title":" ","content":"body"},{"title":"ok","content":""},{"title":"ok","content":"body","author_id":999}]:
            self.assertEqual(c.post("/posts",json=body,headers=headers).status_code,422)

if __name__ == "__main__":
    unittest.main(verbosity=2)

