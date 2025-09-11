from contextlib import contextmanager
from typing import Iterator
import json

from fastapi.exceptions import HTTPException
from fastapi.responses import JSONResponse
from fastapi import FastAPI, HTTPException, status, Query, Body, Path

from sqlalchemy.orm import declarative_base
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import sessionmaker, Session

from pydantic import BaseModel, EmailStr, Field

from typing import Optional, List, Literal

from dotenv import load_dotenv

import os

load_dotenv()

app = FastAPI()

# Configuração do banco de dados
DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Modelo SQLAlchemy
class UsuarioDB(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True)
    ativo = Column(Integer, nullable=False, default=1)

# Criar tabelas
Base.metadata.create_all(bind=engine)

@contextmanager
def Database() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Modelos Pydantic
class UsuarioBase(BaseModel):
    id: Optional[int] = None
    nome: str
    email: EmailStr
    ativo: int = Field(default=1, description="1: ativo | 0: inativo")

class SetUser(UsuarioBase):
    pass

    class Config:
        from_attributes = True

# Rotas
@app.get("/", response_model=dict, 
        summary="Página inicial",
        description="Redireciona para a documentação interativa da API (Swagger UI).") 
def home():
    return {"escreva na URL": "http://127.0.0.1:5000/docs#/"}

@app.post("/usuarios", 
            status_code=status.HTTP_201_CREATED,
            response_model=SetUser,
            summary="Criar novo usuário",
            description="Cadastra um novo usuário no sistema.",
            responses={
                201: {"description": "Usuário criado com sucesso"},
                400: {"description": "Dados inválidos ou erro no banco de dados"}
            })
def set_user(user_info: SetUser = Body(...)):
    try:
        new_user = UsuarioDB(**user_info.dict(exclude={"id"}))
        with Database() as banco:
            banco.add(new_user)
            banco.flush()
            banco.refresh(new_user)
            if new_user.id:
                user_info.id = new_user.id
            banco.commit()
        return JSONResponse(json.loads(user_info.model_dump_json()), 201)
    except Exception as E:
        if isinstance(E, HTTPException):
            raise E
        else:
            raise HTTPException(400, str(E))

@app.get("/usuarios",
    response_model=List[SetUser],
    summary="Listar usuários",
    description="""Retorna todos os usuários cadastrados. 
                Pode ser filtrado por nome quando fornecido como parâmetro.""",
    responses={
        200: {"description": "Lista de usuários retornada com sucesso"},
        404: {"description": "Nenhum usuário encontrado"}
    })
def get_users(
    id: Optional[int] = Query(None, description="Filtrar por ID"),
    ativo: Literal["-1", "0", "1"] = Query("-1", description="-1: todos | 0: inativos | 1: ativos"),
    nome: Optional[str] = Query(default="", description="Filtrar por nome"),
    ordenador: Literal["id", "nome", "ativo"] = Query(default="id")
):
    try:
        with Database() as banco:
            query = banco.query(UsuarioDB)

            if ativo == "0":
                query = query.filter(UsuarioDB.ativo == 0)
            elif ativo == "1":
                query = query.filter(UsuarioDB.ativo == 1)

            if id and id > 0:
                query = query.filter(UsuarioDB.id == id)

            if nome:
                query = query.filter(UsuarioDB.nome.ilike(f"%{nome.strip()}%"))

            coluna_ordenacao = getattr(UsuarioDB, ordenador)
            query = query.order_by(coluna_ordenacao.asc())

            db_users = query.all()

            if not db_users:
                raise HTTPException(status_code=404, detail="Nenhum usuário encontrado")
            
            return db_users
    except Exception as E:
        if isinstance(E, HTTPException):
            raise E
        else:
            raise HTTPException(400, str(E))

@app.patch("/usuarios",
            response_model=SetUser,
            summary="Atualizar usuário",
            description="Atualiza os dados de um usuário existente pelo seu ID.",
            responses={
                200: {"description": "Usuário atualizado com sucesso"},
                400: {"description": "Dados inválidos"},
                404: {"description": "Usuário não encontrado"}
            })
def update_user(user_info: SetUser = Body(..., title="Dados do usuário para atualização")
):
    try:
        with Database() as banco:
            db_user = banco.query(UsuarioDB).filter(
                UsuarioDB.id == user_info.id
            ).update(
                user_info.model_dump(exclude_unset=True, exclude={"id"})
            )
            if db_user:
                banco.commit()
            else:
                raise HTTPException(400, 'Usuário já cadastrado')
        return JSONResponse(json.loads(user_info.model_dump_json()), 200)
    except Exception as E:
        if isinstance(E, HTTPException):
            raise E
        else:
            raise HTTPException(400, str(E))

@app.patch("/usuarios/{user_id}",
           response_model=SetUser,
           summary="Ativar usuário",
           description="Ativa um usuário pelo seu ID.",
           responses={
               200: {"description": "Usuário atualizado com sucesso"},
               400: {"description": "Dados inválidos"},
               404: {"description": "Usuário não encontrado"}
           })
def activate_user(user_id: int = Path(..., title="ID do usuário", description="ID do usuário a ser ativado")):
    try:
        with Database() as banco:
            db_user = banco.query(UsuarioDB).filter(
                UsuarioDB.id == user_id
            ).update(
                {"ativo": 1}
            )
            if db_user:
                banco.commit()
                raise HTTPException(200, 'Usuário ativado com sucesso')
            else:
                raise HTTPException(404, 'Usuário não encontrado')
    except Exception as E:
        if isinstance(E, HTTPException):
            raise E
        else:
            raise HTTPException(400, str(E))

@app.delete("/usuarios/{user_id}", 
            status_code=status.HTTP_204_NO_CONTENT,
            summary="Desativar usuário",
            description="Exclui logicamente um usuário do sistema pelo seu ID.",
            responses={
                204: {"description": "Usuário removido com sucesso"},
                404: {"description": "Usuário não encontrado"},
                500: {"description": "Erro interno no servidor"}
            })
def delete_user(user_id: int = Path(..., title="ID do usuário", description="ID do usuário a ser removido")):
    try:
        with Database() as banco:
            usuario = banco.query(UsuarioDB).filter(
                UsuarioDB.id == user_id
            ).update(
                {"ativo": 0}
            )
            if not usuario:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Usuário não encontrado"
                )
            banco.commit()
            raise HTTPException(200, 'Usuário excluído com sucesso')
    except Exception as E:
        if isinstance(E, HTTPException):
            raise E
        else:
            raise HTTPException(400, str(E))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=5000,
        reload=True,
        workers=1
    )
