"""독립된 메모리 SQLite로 요청 검증/인증/작성자 권한을 확인. PostgreSQL 검증과 구분."""
import asyncio
import os
import secrets
import threading
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
os.environ["BOARD_TESTING"] = "1"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["JWT_SECRET"] = secrets.token_hex(32)
import jwt
from fastapi.testclient import TestClient
from database import Base, engine, get_db
from main import app
from security import SECRET, hash_password, verify_password

class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(app, raise_server_exceptions=False)
        cls.client = cls.context.__enter__()
        async def prepare():
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
        cls.client.portal.call(prepare)

    @classmethod
    def tearDownClass(cls):
        # TestClient 종료가 앱 lifespan의 엔진 정리를 실행한다.
        cls.context.__exit__(None, None, None)

    def override_db(self, session):
        async def replacement():
            yield session
        app.dependency_overrides[get_db] = replacement
        self.addCleanup(app.dependency_overrides.pop, get_db, None)

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status)
        body = response.json()
        self.assertEqual(set(body), {"error"})
        self.assertEqual(set(body["error"]), {"code", "message", "details"})
        self.assertEqual(body["error"]["code"], code)
        self.assertIsInstance(body["error"]["message"], str)
        self.assertIsInstance(body["error"]["details"], list)
        return body["error"]

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

    def test_error_envelopes_hide_validation_inputs_and_keep_headers(self):
        c = self.client
        response = c.post("/auth/signup", json={
            "email": "private-invalid-email", "password": "S3cr!", "private-token-field": "private-token-value",
        })
        error = self.assert_error(response, 422, "validation_error")
        self.assertTrue(error["details"])
        for sensitive in ("private-invalid-email", "S3cr!", "private-token-field", "private-token-value"):
            self.assertNotIn(sensitive, response.text)
        for detail in error["details"]:
            self.assertEqual(set(detail), {"location", "code", "message"})
        self.assert_error(c.get("/not-a-route"), 404, "not_found")
        self.assert_error(c.get("/posts/999999"), 404, "not_found")
        wrong_method = c.get("/auth/signup")
        self.assert_error(wrong_method, 405, "method_not_allowed")
        self.assertIn("POST", wrong_method.headers["Allow"])
        unauthorized = c.post("/posts", json={"title": "title", "content": "body"})
        self.assert_error(unauthorized, 401, "unauthorized")
        self.assertEqual(unauthorized.headers["WWW-Authenticate"], "Bearer")
        user = {"email": "envelope@example.test", "password": "test-password-2026"}
        self.assertEqual(c.post("/auth/signup", json=user).status_code, 201)
        self.assert_error(c.post("/auth/signup", json=user), 409, "conflict")

    def test_health_checks_database_and_masks_connection_failure(self):
        healthy = self.client.get("/health")
        self.assertEqual(healthy.status_code, 200)
        self.assertEqual(healthy.json(), {"status": "ok", "database": "ok"})
        failed = SimpleNamespace(scalar=AsyncMock(side_effect=RuntimeError("private-database-connection")))
        self.override_db(failed)
        response = self.client.get("/health")
        self.assert_error(response, 503, "service_unavailable")
        self.assertNotIn("private-database-connection", response.text)
        failed.scalar.assert_awaited_once()

    def test_unexpected_error_uses_safe_envelope(self):
        failed = SimpleNamespace(scalars=AsyncMock(side_effect=RuntimeError("private-internal-token")))
        self.override_db(failed)
        response = self.client.get("/posts")
        error = self.assert_error(response, 500, "internal_error")
        self.assertEqual(error["details"], [])
        self.assertNotIn("private-internal-token", response.text)

    def test_password_hashing_runs_outside_async_request_thread(self):
        request_thread = self.client.portal.call(threading.get_ident)
        hashing_threads = []
        verification_threads = []
        def hash_in_worker(password):
            hashing_threads.append(threading.get_ident())
            return hash_password(password)
        def verify_in_worker(password, saved):
            verification_threads.append(threading.get_ident())
            return verify_password(password, saved)
        user = {"email": "threadpool@example.test", "password": "test-password-2026"}
        with patch("main.hash_password", side_effect=hash_in_worker), patch("main.verify_password", side_effect=verify_in_worker):
            self.assertEqual(self.client.post("/auth/signup", json=user).status_code, 201)
            result = self.client.post("/auth/token", data={"username": user["email"], "password": user["password"]})
            self.assertEqual(result.status_code, 200)
        self.assertEqual(len(hashing_threads), 1)
        self.assertEqual(len(verification_threads), 1)
        self.assertTrue(all(worker != request_thread for worker in hashing_threads + verification_threads))

    def test_oversized_login_password_skips_lookup_and_hashing(self):
        session = SimpleNamespace(scalar=AsyncMock(side_effect=AssertionError("Database lookup must not run")))
        self.override_db(session)
        with patch("main.verify_password") as verify:
            result = self.client.post("/auth/token", data={"username": "threadpool@example.test", "password": "x" * 129})
            self.assert_error(result, 401, "unauthorized")
            self.assertEqual(result.headers["WWW-Authenticate"], "Bearer")
            verify.assert_not_called()
        session.scalar.assert_not_awaited()

    def test_password_salts_and_malformed_hashes(self):
        first = hash_password("test-password-2026")
        second = hash_password("test-password-2026")
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("test-password-2026", first))
        self.assertFalse(verify_password("different-password", first))
        for malformed in ("", "not-a-hash", "xx:yy", None):
            self.assertFalse(verify_password("test-password-2026", malformed))
        with patch("security.hashlib.scrypt") as scrypt:
            self.assertFalse(verify_password("x" * 129, first))
            scrypt.assert_not_called()

    def test_openapi_describes_health_and_standard_errors(self):
        schema = self.client.get("/openapi.json").json()
        expected = {"$ref": "#/components/schemas/ErrorResponse"}
        for path, method, status in (("/auth/signup", "post", "422"), ("/posts", "get", "500"), ("/health", "get", "503")):
            self.assertEqual(schema["paths"][path][method]["responses"][status]["content"]["application/json"]["schema"], expected)
        self.assertIn("WWW-Authenticate", schema["paths"]["/posts"]["post"]["responses"]["401"]["headers"])

if __name__ == "__main__":
    unittest.main(verbosity=2)

