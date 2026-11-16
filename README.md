# FastAPI 게시판

FastAPI와 PostgreSQL을 사용한 게시판 API. 가입과 로그인으로 JWT를 발급하고, 로그인한 회원만 글을 작성할 수 있다. 글 수정과 삭제는 작성자만 할 수 있다.

## 실행

1. PostgreSQL에 새 데이터베이스를 준비한다.
2. `.env.example`을 `.env`로 복사해 `DATABASE_URL`과 `JWT_SECRET`을 설정한다.
3. 프로젝트 폴더에서 아래 명령을 실행한다.

```bash
uv sync --locked
uv run python init_db.py
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

[Swagger UI](http://127.0.0.1:8000/docs)에서 가입한 뒤 **Authorize**의 username 칸에 가입 이메일을 입력한다.

| 메서드 | 경로 | 동작 |
| --- | --- | --- |
| POST | `/auth/signup` | 가입 |
| POST | `/auth/token` | 로그인 및 토큰 발급 |
| GET, POST | `/posts` | 글 목록 조회 및 작성 |
| GET, PUT, DELETE | `/posts/{post_id}` | 글 상세 조회, 수정 및 삭제 |

목록과 상세 조회는 로그인 없이 가능하다. 글 작성 시 작성자 ID는 요청 본문에서 받지 않고 인증된 회원의 ID를 사용한다.

`uv run python test_api.py`로 가입, 로그인, 게시글 CRUD, 작성자 권한에 대한 테스트를 실행할 수 있다.
