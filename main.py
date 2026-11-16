from contextlib import asynccontextmanager
from typing import Annotated
import jwt
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from database import engine, get_db
from models import User, Post
from schemas import Signup, UserOut, Token, PostInput, PostOut, ErrorBody, ErrorDetail, ErrorResponse, HealthOut
from security import MAX_PASSWORD_LENGTH, hash_password, verify_password, create_token, decode_user_id

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        await engine.dispose()

ERROR_CODES = {
    400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
    405: "method_not_allowed", 409: "conflict", 422: "validation_error",
    500: "internal_error", 503: "service_unavailable",
}
app = FastAPI(
    title="석호의 최소 게시판 API", version="1.0", lifespan=lifespan,
    description="회원가입과 JWT 로그인, 작성자만 수정/삭제 가능한 게시판 API. 오류는 error.code/message/details 형식으로 반환합니다.",
    responses={status: {
        "model": ErrorResponse, "description": code,
        **({"headers": {"WWW-Authenticate": {"description": "Bearer 인증 방식", "schema": {"type": "string"}}}}
           if status == 401 else {}),
    } for status, code in ERROR_CODES.items()},
)
oauth = OAuth2PasswordBearer(tokenUrl="/auth/token")
Db = Annotated[AsyncSession, Depends(get_db)]
Id = Annotated[int, Path(gt=0)]

def error_response(status: int, code: str, message: str, *, details=None, headers=None):
    body = ErrorResponse(error=ErrorBody(code=code, message=message, details=details or []))
    return JSONResponse(status_code=status, content=body.model_dump(), headers=headers)

@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, error: StarletteHTTPException):
    message = error.detail if isinstance(error.detail, str) else "요청을 처리할 수 없습니다"
    if error.status_code >= 500:
        message = "데이터베이스 연결을 사용할 수 없습니다" if error.status_code == 503 else "서버 오류가 발생했습니다"
    return error_response(error.status_code, ERROR_CODES.get(error.status_code, "http_error"), message,
                          headers=error.headers)

VALIDATION_MESSAGES = {
    "missing": "필수 항목입니다", "extra_forbidden": "허용되지 않는 항목입니다",
    "string_type": "문자열을 입력하세요", "string_too_short": "문자열이 너무 짧습니다",
    "string_too_long": "문자열이 너무 깁니다", "string_pattern_mismatch": "형식이 올바르지 않습니다",
    "int_parsing": "정수를 입력하세요", "int_type": "정수를 입력하세요",
    "greater_than": "허용된 최솟값보다 커야 합니다", "greater_than_equal": "허용된 최솟값 이상이어야 합니다",
    "less_than": "허용된 최댓값보다 작아야 합니다", "less_than_equal": "허용된 최댓값 이하여야 합니다",
    "json_invalid": "올바른 JSON을 입력하세요",
}
VALIDATION_LOCATIONS = {
    "body", "query", "path", "header", "cookie", "email", "password", "username",
    "title", "content", "author_id", "post_id", "offset", "limit", "grant_type", "scope",
    "client_id", "client_secret",
}

@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, error: RequestValidationError):
    details = []
    for item in error.errors():
        code = item.get("type", "invalid_value")
        if code not in VALIDATION_MESSAGES:
            code = "invalid_value"
        location = [part if type(part) is int or part in VALIDATION_LOCATIONS else "unknown_field"
                    for part in item.get("loc", ())]
        details.append(ErrorDetail(location=location, code=code,
                                   message=VALIDATION_MESSAGES.get(code, "입력값이 올바르지 않습니다")))
    return error_response(422, "validation_error", "입력값을 확인하세요", details=details)

@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception):
    return error_response(500, "internal_error", "서버 오류가 발생했습니다")

@app.get("/health", response_model=HealthOut, tags=["운영"], summary="데이터베이스 연결 상태 확인")
async def health(db: Db):
    try:
        result = await db.scalar(text("SELECT 1"))
    except Exception:
        raise HTTPException(503, "데이터베이스 연결을 사용할 수 없습니다") from None
    if result != 1:
        raise HTTPException(503, "데이터베이스 연결을 사용할 수 없습니다")
    return HealthOut()

async def current_user(db: Db, token: Annotated[str, Depends(oauth)]) -> User:
    try:
        user_id = decode_user_id(token)
    except (jwt.PyJWTError, ValueError, TypeError, KeyError):
        raise HTTPException(401, "유효하지 않거나 만료된 토큰", headers={"WWW-Authenticate": "Bearer"})
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(401, "존재하지 않는 회원", headers={"WWW-Authenticate": "Bearer"})
    return user

CurrentUser = Annotated[User, Depends(current_user)]

@app.post("/auth/signup", response_model=UserOut, status_code=201)
async def signup(data: Signup, db: Db):
    password_hash = await run_in_threadpool(hash_password, data.password)
    user = User(email=data.email, password_hash=password_hash)
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "이미 등록된 이메일")
    await db.refresh(user)
    return user

@app.post("/auth/token", response_model=Token)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: Db):
    if len(form.password) > MAX_PASSWORD_LENGTH:
        raise HTTPException(401, "이메일 또는 비밀번호가 맞지 않습니다", headers={"WWW-Authenticate": "Bearer"})
    user = await db.scalar(select(User).where(User.email == form.username.strip().lower()))
    if user is None or not await run_in_threadpool(verify_password, form.password, user.password_hash):
        raise HTTPException(401, "이메일 또는 비밀번호가 맞지 않습니다", headers={"WWW-Authenticate": "Bearer"})
    return Token(access_token=create_token(user.id))

@app.post("/posts", response_model=PostOut, status_code=201)
async def create_post(data: PostInput, db: Db, user: CurrentUser):
    post = Post(**data.model_dump(), author_id=user.id)
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post

@app.get("/posts", response_model=list[PostOut])
async def list_posts(db: Db, offset: int = Query(0, ge=0), limit: int = Query(20, ge=1, le=100)):
    result = await db.scalars(select(Post).order_by(Post.id.desc()).offset(offset).limit(limit))
    return list(result)

async def find_post(post_id: int, db: AsyncSession):
    post = await db.get(Post, post_id)
    if post is None:
        raise HTTPException(404, "게시글이 없습니다")
    return post

@app.get("/posts/{post_id}", response_model=PostOut)
async def read_post(post_id: Id, db: Db):
    return await find_post(post_id, db)

@app.put("/posts/{post_id}", response_model=PostOut)
async def update_post(post_id: Id, data: PostInput, db: Db, user: CurrentUser):
    post = await find_post(post_id, db)
    if post.author_id != user.id:
        raise HTTPException(403, "작성자만 수정할 수 있습니다")
    post.title, post.content = data.title, data.content
    await db.commit()
    await db.refresh(post)
    return post

@app.delete("/posts/{post_id}", status_code=204)
async def delete_post(post_id: Id, db: Db, user: CurrentUser):
    post = await find_post(post_id, db)
    if post.author_id != user.id:
        raise HTTPException(403, "작성자만 삭제할 수 있습니다")
    await db.delete(post)
    await db.commit()
    return Response(status_code=204)

