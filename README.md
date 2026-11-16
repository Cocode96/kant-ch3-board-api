# FastAPI 게시판 API

KANT CH3 백엔드 아키텍처 & API 설계 과제. FastAPI, SQLAlchemy 비동기 세션, PostgreSQL을 사용한다. 회원가입과 비밀번호 로그인으로 JWT를 발급하고, 게시글 수정과 삭제는 작성자에게만 허용한다.

## 제출 주소와 검증 상태

- GitHub: <https://github.com/Cocode96/kant-ch3-board-api>
- EC2 서비스 / Swagger: <https://43.201.32.243/docs>
- OpenAPI: <https://43.201.32.243/openapi.json>
- 2026-11-17 실제 배포 서버의 HTTPS API 검증 27개 통과. 기존 가입/로그인과 작성자 권한, 게시글 CRUD를 확인했다.
- 로컬 보완 코드의 회귀 테스트 10개 통과. 공통 오류 모델과 `/health`는 보완 코드에 있으며 현재 EC2에는 아직 반영하지 않았다.
- 서버 내부 PostgreSQL 연결과 프로세스 재시작 후 데이터 보존은 SSH 접속이 막혀 확인하지 못했다. 실제 API 검증과 구분한다.

## 실제 서비스 검증

두 개의 고유한 검증 계정으로 HTTPS 요청을 실행했다. 비밀번호와 토큰은 결과 파일에 포함하지 않았다.

| 확인 항목 | 실제 응답과 결과 |
| --- | --- |
| `/docs`, `/openapi.json` | HTTPS 200, 인증서 검증 유지 |
| A/B 회원가입과 로그인 | 201 / 200, 회원 응답에 비밀번호 해시 없음 |
| 비로그인 글 작성 | 401과 Bearer 인증 헤더 |
| A의 글 작성과 목록/상세 조회 | 201 / 200, 작성자 ID는 서버가 지정 |
| B의 A 글 수정과 삭제 | 각각 403, 원본 내용 유지 |
| A의 수정과 새 세션 재로그인/조회 | 200, 저장된 수정 내용 유지 |
| 공백 제목, 작성자 ID 주입, 잘못된 페이지 매개변수 | 422 |
| 잘못된 JWT | 401 |
| A의 검증 게시글 삭제와 재조회 | 204 / 404, 검증 게시글 정리 완료 |

[27개 API 검증 결과](evidence/live-api-verification.json)

![EC2에서 열린 실제 Swagger UI](evidence/ec2-swagger.jpg)

위 캡처와 실제 검증은 배포되어 있던 기존 API를 대상으로 했다. 이 README의 공통 오류 모델과 `/health` 설명은 로컬 보완 코드 기준이다. 테스트 회원 두 개는 회원 삭제 API가 없어 서버 접속 후 정리할 대상으로 기록했다. 새 세션 조회는 확인했지만 서버 재시작 검증은 하지 않았다.

## 실행

Python 3.13 이상과 uv가 필요하다. 기존 과제용 PostgreSQL의 연결 정보를 `.env`에 설정한다.

```bash
uv sync --locked
cp .env.example .env
```

| 환경변수 | 설정 |
| --- | --- |
| `DATABASE_URL` | `postgresql+asyncpg://USER:PASSWORD@HOST:5432/DB_NAME` |
| `JWT_SECRET` | 과제 앱 전용으로 생성한 32자 이상의 무작위 값 |

`.env`와 키 파일은 Git에 올리지 않는다. 비밀번호에 URL 예약 문자가 있으면 연결 문자열에서 인코딩한다. DB 사용자에게 해당 과제 DB에 필요한 권한만 부여한다.

```bash
uv run python init_db.py
uv run uvicorn main:app --host 127.0.0.1 --port 8000
```

`init_db.py`는 없는 테이블을 생성하며 기존 테이블을 삭제하지 않는다. 스키마 변경을 자동 적용하는 마이그레이션 도구는 아니다. 앱 시작 시 테이블을 자동 생성하지 않는다.

로컬 API 문서는 <http://127.0.0.1:8000/docs>, OpenAPI 명세는 `/openapi.json`이다. Swagger에서 `POST /auth/signup`으로 가입한 후 **Authorize**의 `username`에 가입 이메일, `password`에 가입 비밀번호를 입력한다.

## API와 권한

| 메서드 | 경로 | 성공 응답 | 권한과 동작 |
| --- | --- | --- | --- |
| POST | `/auth/signup` | 201 | 이메일과 비밀번호로 가입 |
| POST | `/auth/token` | 200 | form 형식의 username/password로 JWT 발급 |
| GET | `/posts` | 200 | 공개 목록, offset/limit 페이지 구분 |
| POST | `/posts` | 201 | 로그인한 회원이 글 작성 |
| GET | `/posts/{post_id}` | 200 | 공개 상세 조회 |
| PUT | `/posts/{post_id}` | 200 | 작성자만 제목과 본문 전체 수정 |
| DELETE | `/posts/{post_id}` | 204 | 작성자만 삭제, 응답 본문 없음 |
| GET | `/health` | 200 | DB에 `SELECT 1` 실행, 연결 실패 시 503 |

글 작성 시 `author_id`는 JWT로 확인한 회원 ID로 지정한다. 요청 본문에 작성자를 지정하거나 정의되지 않은 필드를 넣으면 422로 거절한다. 인증 누락/잘못된 토큰/만료 토큰은 401, 다른 작성자의 수정과 삭제는 403, 없는 글은 404, 중복 이메일은 409다.

제목은 공백 제거 후 1~200자, 본문은 1~10,000자다. 이메일은 앞뒤 공백 제거와 소문자 정규화를 적용하며, 가입 비밀번호는 8~128자다. 목록은 최신 ID부터 반환하고 `offset >= 0`, `1 <= limit <= 100`으로 조회량을 제한한다.

HTTP 오류와 입력 검증 오류는 다음 형식으로 통일하고 OpenAPI에도 같은 모델을 명시한다.

```json
{
  "error": {
    "code": "validation_error",
    "message": "입력값을 확인하세요",
    "details": [
      {"location": ["body", "title"], "code": "string_too_short", "message": "문자열이 너무 짧습니다"}
    ]
  }
}
```

오류 응답에는 비밀번호, 토큰, 요청 입력값, 내부 예외 문구를 포함하지 않는다. 401 응답의 `WWW-Authenticate: Bearer` 헤더를 유지한다. `/health`는 DB 연결만 점검하며 테이블 존재나 전체 CRUD 성공을 대신하지 않는다.

## 데이터와 코드 구조

```mermaid
erDiagram
    board_users ||--o{ board_posts : writes
    board_users {
        int id PK
        varchar email UK
        varchar password_hash
    }
    board_posts {
        int id PK
        varchar title
        text content
        int author_id FK
        timestamptz created_at
    }
```

`board_posts.author_id`는 `board_users.id`를 참조하며 인덱스를 사용한다. `ON DELETE RESTRICT`로 게시글이 남은 회원의 삭제를 제한하고, 제목과 본문은 DB CHECK 제약도 적용한다. 목록은 게시글 테이블을 한 번 조회하며 회원 정보를 반복 조회하는 N+1 쿼리가 없다.

| 파일 | 책임 |
| --- | --- |
| `main.py` | HTTP 경로, 인증 의존성, 작성자 권한과 트랜잭션 |
| `schemas.py` | 요청 검증과 응답 직렬화 |
| `models.py` | 테이블, PK/FK, 인덱스와 제약조건 |
| `database.py` | 환경 설정, 비동기 엔진과 요청별 세션, 오류 시 rollback |
| `security.py` | 비밀번호 해싱과 검증, JWT 생성과 해석 |
| `init_db.py` | 명시적으로 실행하는 테이블 초기화 |
| `test_api.py` | 독립 DB에서 실행하는 회귀 검증 |

비밀번호는 회원마다 무작위 salt를 사용한 scrypt 해시로 저장하며 응답에 포함하지 않는다. 해시 연산은 스레드풀에서 실행해 비동기 이벤트 루프를 직접 막지 않도록 한다. 로그인 비밀번호가 128자를 넘으면 해시 연산 전에 거절한다. JWT는 HS256 알고리즘만 허용하고 `sub`, `exp`를 필수 검증한다. 만료 시간은 30분이며, refresh token과 서버 측 즉시 토큰 폐기는 구현하지 않았다.

## 검증과 운영 범위

```bash
uv run --locked python -B test_api.py
```

테스트는 `BOARD_TESTING=1`과 메모리 SQLite를 사용하므로 실제 회원이나 게시글을 변경하지 않는다. 회원 A와 B의 가입/로그인, A의 CRUD, B의 수정/삭제 403과 원본 보존, 잘못된 입력, 중복 이메일, 만료 토큰, 작성자 ID 위조 거절, Swagger 명세를 확인한다.

추가 회귀 검증은 공통 오류 모델과 인증 헤더, 입력값/내부 오류 비노출, DB 상태 확인의 성공/실패, 해시 연산의 스레드 분리, 과도한 비밀번호 길이의 사전 차단, 무작위 salt와 잘못된 해시 처리, OpenAPI 오류 스키마를 포함한다. Python 3.13.14에서 10개 테스트를 통과했다. Starlette의 httpx TestClient 관련 deprecation 경고가 한 번 출력되며 실패는 없었다.

운영 DB는 PostgreSQL asyncpg 연결만 허용한다. 요청별 세션과 `pool_pre_ping`을 사용하며 실패한 트랜잭션은 rollback한다. EC2에서는 기존 프로세스 관리자와 프록시 설정을 먼저 확인하고, 배포 전 DB 백업과 현재 버전을 보존해야 한다. 환경변수와 DB 파일을 코드 배포로 덮어쓰지 않는다.

외부 EC2 HTTPS 접속과 기존 API 동작은 위의 실제 검증에서 확인했다. 보완 코드 배포와 서버 내부 확인은 남아 있다. 파일 업로드, 캐시, 부하 테스트는 구현/검증 범위에 포함하지 않는다.
