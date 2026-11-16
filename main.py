from typing import Annotated
import jwt
from fastapi import Depends, FastAPI, HTTPException, Path, Query, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models import User, Post
from schemas import Signup, UserOut, Token, PostInput, PostOut
from security import hash_password, verify_password, create_token, decode_user_id

app = FastAPI(title="석호의 최소 게시판 API", version="1.0")
oauth = OAuth2PasswordBearer(tokenUrl="/auth/token")
Db = Annotated[AsyncSession, Depends(get_db)]
Id = Annotated[int, Path(gt=0)]

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
    user = User(email=data.email, password_hash=hash_password(data.password))
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
    user = await db.scalar(select(User).where(User.email == form.username.strip().lower()))
    if user is None or not verify_password(form.password, user.password_hash):
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

