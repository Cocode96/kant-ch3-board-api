# FastAPI 게시판 API

KANT CH3 백엔드 아키텍처 & API 설계 과제. FastAPI, SQLAlchemy 비동기 세션, PostgreSQL을 사용한다. 회원가입과 비밀번호 로그인으로 JWT를 발급하고, 게시글 수정과 삭제는 작성자에게만 허용한다.

## 제출 주소와 검증 상태

- GitHub: <https://github.com/Cocode96/kant-ch3-board-api>
- EC2 서비스 / Swagger: <https://43.201.32.243/docs>
- OpenAPI: <https://43.201.32.243/openapi.json>
- 2026-11-17 KST, 기존 EC2에 공통 오류 모델과 `/health`를 포함한 보완 코드 배포 완료. 검증 시 배포 커밋은 `566b98a`다.
- 기존 배포의 HTTPS API 27개, 보완 코드 배포 후 API 21개, 서버 인증/데이터 정리 검증 8개가 각각 통과했다.
- 회귀 테스트 10개는 로컬 Python 3.13.14와 EC2 Python 3.15.2에서 각각 통과했다. 이 테스트의 DB는 메모리 SQLite이며, 실제 PostgreSQL 검증은 별도로 수행했다.
- 실제 PostgreSQL 16.15 연결, 앱 서비스 재시작 후 게시글 보존, DB 백업의 임시 DB 복원과 행 수 일치를 확인했다. 검증 게시글과 검증 회원 2개는 정리했고 기존 회원은 보존했다.

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
| 보완 코드의 `/health` | 200, `status=ok`, `database=ok` |
| 보완 코드의 401/403/404/405/422 | 공통 오류 모델, 인증 헤더 유지, 입력값 비노출 |
| 실제 DB 드라이버와 서버 버전 | `postgresql+asyncpg`, PostgreSQL 16.15 |
| 앱 서비스 재시작 후 A/B 재로그인과 상세 조회 | 로그인 200, 수정한 제목과 작성자 유지 |
| 서버 키로 정상 서명한 만료 JWT | 401, `unauthorized` |
| 검증 회원 정리 후 로그인 | 두 계정 모두 401, 기존 회원과 게시글 보존 |

검증 기록은 실행 단계를 구분한다. [초기 배포 API 27개](evidence/live-api-verification.json)는 기존 `99ae907` 코드에서 실행했다. [보완 코드 배포 후 API 21개](evidence/updated-deployment-verification.json), [서버 인증과 정리 8개](evidence/server-runtime-verification.json), [최종 HTTPS 확인](evidence/final-public-verification.json)은 `566b98a` 배포 후의 기록이다. 계정 이메일, 비밀번호, 토큰과 비밀키는 공개하지 않는다.

![EC2에서 열린 실제 Swagger UI](evidence/ec2-swagger.jpg)

![Swagger Try it out으로 확인한 실제 DB 상태 200 응답](evidence/ec2-health.jpg)

캡처는 보완 코드 배포 후의 실제 HTTPS 화면이다. 만료 토큰 검증은 서버의 실제 서명 키로 만료 시각을 과거로 지정한 토큰을 만들어 수행했으며, 같은 키로 서명한 유효 토큰이 입력 검증 단계까지 도달하는 것도 확인했다. 30분을 기다린 시험은 아니다. 재시작 검증은 EC2 전체 재부팅이 아니라 `kantboard.service` 재시작이다.

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

추가 회귀 검증은 공통 오류 모델과 인증 헤더, 입력값/내부 오류 비노출, DB 상태 확인의 성공/실패, 해시 연산의 스레드 분리, 과도한 비밀번호 길이의 사전 차단, 무작위 salt와 잘못된 해시 처리, OpenAPI 오류 스키마를 포함한다. 로컬 Python 3.13.14와 EC2 Python 3.15.2에서 각각 10개 테스트를 통과했다. Starlette의 httpx TestClient 관련 deprecation 경고가 출력되며 실패는 없었다.

운영 DB는 PostgreSQL asyncpg 연결만 허용한다. 요청별 세션과 `pool_pre_ping`을 사용하며 실패한 트랜잭션은 rollback한다.

## 기존 EC2 배포 구성과 복구

```mermaid
flowchart LR
    Client[브라우저 / API 클라이언트] -->|HTTPS 443| Nginx[Nginx]
    Nginx -->|127.0.0.1:8000| API[Uvicorn / FastAPI]
    API -->|asyncpg / 127.0.0.1:5432| DB[(PostgreSQL)]
    Systemd[systemd kantboard.service] -. 실행과 재시작 .-> API
```

기존 Ubuntu 24.04 EC2와 `kantboard.service`를 그대로 사용했다. 앱은 전용 `kantboard` 사용자로 실행하며 DB와 Uvicorn은 루프백 주소에서 수신한다. Nginx 설정 검사와 서비스 실행 상태를 확인했다. 환경변수는 Git 밖의 `/etc/kantboard.env`에 두고 root 전용 권한 `600`으로 관리한다.

[서버 명령 실행 결과 요약](evidence/operations-verification.json)에 회귀 테스트, 백업 복원, 재시작과 서비스 상태를 기록했다. 이 파일은 실제 명령 출력을 정리한 기록이며 API 자동 검증 JSON과 구분한다.

배포 전 `pg_dump` 백업, 기존 소스, 서비스 설정과 환경 설정을 서버의 root 전용 백업 디렉터리에 보관했다. DB 백업은 별도의 임시 DB에 복원해 회원 4행과 게시글 0행이 원본과 일치하는지 확인한 후 임시 DB만 삭제했다. 이후 기존 Git 작업 트리에서 fast-forward 배포하고 서비스를 재시작했다. 스키마와 의존성은 변경하지 않았다.

게시글을 새로 저장한 다음 서비스를 다시 시작해 프로세스 교체와 DB의 게시글 1행 보존을 확인했다. HTTPS 상세 조회에서도 수정 내용과 작성자가 유지됐고 검증 후 해당 글을 삭제했다. 검증 회원은 정확한 ID/이메일과 작성 글이 없음을 확인한 뒤 트랜잭션으로 2개만 삭제했다. 원래 회원 2개는 그대로 남았다.

장애 시에는 먼저 `journalctl -u kantboard.service`와 `/health`를 확인한다. 이번 배포의 이전 버전은 `99ae907`이며 서버 백업의 `previous-revision.txt`와 소스 아카이브에 기록돼 있다. 소스 복구가 필요하면 서비스를 멈추고 해당 버전을 복원한 뒤 다시 시작한다. DB 복원은 현재 데이터를 별도로 백업한 후 필요할 때만 수행한다. 이번에는 임시 DB 복원 검증까지 수행했으며 운영 DB를 과거 상태로 되돌리지는 않았다.

HTTPS는 인증서 검증을 끄지 않은 상태에서 TLS 1.3 연결을 확인했다. `kantboard-certbot-renew.timer`가 활성화돼 있고 마지막 갱신 작업의 종료 상태는 성공이었다. 확인 시 인증서 만료 시각은 2026-11-23 04:36:22 UTC이며 이후 갱신 결과는 운영 중 점검해야 한다.

파일 업로드, 캐시, 부하 테스트와 EC2 전체 재부팅은 이번 구현/검증 범위에 포함하지 않는다.
