#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import locale
import sys
import os
import uvicorn

# =============================================================================
# CONFIGURAÇÃO DE ENCODING E LOCALE
# =============================================================================
# CRÍTICO: Configuração para suportar caracteres especiais (ç, ã, õ, etc.)
# Esta seção resolve o erro: 'utf-8' codec can't decode byte 0xe7

# Configurar encoding padrão/NÃO REMOVER - força UTF-8 em toda saída do Python
sys.stdout.reconfigure(encoding='utf-8', errors='ignore')
sys.stderr.reconfigure(encoding='utf-8', errors='ignore')

# Tentar definir locale do sistema para UTF-8 com fallbacks
try:
    locale.setlocale(locale.LC_ALL, 'C.UTF-8')      # Primeira opção: locale C universal
except locale.Error:
    try:
        locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')  # Segunda opção: locale americano
    except locale.Error:
        print("Aviso: Não foi possível definir locale UTF-8")

# =============================================================================
# IMPORTS E DEPENDÊNCIAS
# =============================================================================
from contextlib import contextmanager    # Para gerenciamento de conexões de banco
from typing import Iterator              # Type hints para geradores
import json                             # Manipulação de dados JSON

# Framework FastAPI e componentes relacionados
from fastapi.exceptions import HTTPException    # Exceções HTTP customizadas
from fastapi.responses import JSONResponse      # Respostas JSON
from fastapi import FastAPI, HTTPException, status, Query, Body, Path, Form, Depends, Request
from fastapi.responses import Response
from fastapi import APIRouter                   # Roteamento de endpoints
from fastapi.middleware.cors import CORSMiddleware  # Middleware para CORS

# SQLAlchemy ORM para banco de dados
from sqlalchemy.orm import selectinload, with_loader_criteria, declarative_base
from sqlalchemy import create_engine, Column, Integer, String, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy import URL                      # Construtor de URLs de conexão

# Pydantic para validação de dados
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Literal

# Carregar variáveis de ambiente do arquivo .env
from dotenv import load_dotenv

# =============================================================================
# CARREGAMENTO DE CONFIGURAÇÕES
# =============================================================================
# Forçar encoding UTF-8 ao carregar o arquivo .env - evita problemas com acentos
load_dotenv(encoding='utf-8')

# Debug: verificar se as variáveis de ambiente foram carregadas corretamente
# IMPORTANTE: Essas variáveis vêm do arquivo .env ou do docker-compose.yml
print("=== DEBUG: Variáveis de Ambiente ===")
print(f"DB_NAME: {repr(os.getenv('DB_NAME'))}")        # Nome do banco de dados
print(f"DB_USER: {repr(os.getenv('DB_USER'))}")        # Usuário do PostgreSQL  
print(f"DB_PASSWORD: {repr(os.getenv('DB_PASSWORD'))}")  # Senha do PostgreSQL
print(f"DB_HOST: {repr(os.getenv('DB_HOST'))}")        # Host do PostgreSQL (localhost ou host.docker.internal)
print(f"DB_PORT: {repr(os.getenv('DB_PORT'))}")        # Porta do PostgreSQL (geralmente 5432)
print("=====================================")

# =============================================================================
# VALIDAÇÃO DE VARIÁVEIS DE AMBIENTE
# =============================================================================
# Garantir que todas as variáveis necessárias existam antes de prosseguir
# Se alguma variável estiver faltando, a aplicação para com erro claro
DB_NAME = os.getenv('DB_NAME', 'dever-crud-postgresql')     # Nome do banco com fallback
DB_USER = os.getenv('DB_USER', 'postgres')                 # Usuário com fallback
DB_PASSWORD = os.getenv('DB_PASSWORD', '12345')            # Senha com fallback
DB_HOST = os.getenv('DB_HOST', 'localhost')                # Host com fallback
DB_PORT = os.getenv('DB_PORT', '5432')                     # Porta com fallback

# =============================================================================
# CONFIGURAÇÃO DA APLICAÇÃO FASTAPI
# =============================================================================
# Criar instância do FastAPI com metadados para documentação
app = FastAPI(
    title="CRUD SQLAlchemy API",                              # Nome exibido no Swagger
    description="API para gerenciamento de usuários com PostgreSQL",  # Descrição da API
    version="1.0.0"                                          # Versão da API
)

# =============================================================================
# MIDDLEWARE CORS
# =============================================================================
# Configurar CORS para permitir requisições de qualquer origem
# IMPORTANTE: Em produção, restringir as origens permitidas
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Permite qualquer origem (DEVELOPMENT ONLY!)
    allow_credentials=True,     # Permite envio de cookies/credenciais
    allow_methods=["*"],        # Permite todos os métodos HTTP (GET, POST, etc.)
    allow_headers=["*"],        # Permite todos os cabeçalhos
)

# =============================================================================
# MIDDLEWARE GLOBAL DE TRATAMENTO DE ENCODING
# =============================================================================
# Captura erros de encoding em qualquer endpoint e retorna erro JSON formatado
@app.middleware("http")
async def encoding_error_handler(request: Request, call_next):
    """Middleware para capturar e tratar erros de encoding UTF-8."""
    try:
        response = await call_next(request)
        return response
    except UnicodeDecodeError as e:
        return JSONResponse(
            status_code=400,
            content={
                "detail": f"Erro de codificação de caracteres: {str(e)}",
                "error_type": "encoding_error",
                "suggestion": "Verifique se há caracteres especiais nos dados do banco"
            }
        )
    except Exception as e:
        # Captura erros de encoding que podem estar mascarados como outros tipos
        if "'utf-8' codec can't decode" in str(e):
            return JSONResponse(
                status_code=400,
                content={
                    "detail": f"Erro de codificação UTF-8: {str(e)}",
                    "error_type": "utf8_decode_error",
                    "suggestion": "Dados no banco podem conter caracteres incompatíveis com UTF-8"
                }
            )
        raise e

# =============================================================================
# CONFIGURAÇÃO DO BANCO DE DADOS
# =============================================================================
# Variáveis globais para controle de conexão - inicializadas como None
engine = None           # Engine do SQLAlchemy para conexões com PostgreSQL
SessionLocal = None     # Factory de sessões do banco de dados
Base = declarative_base()  # Classe base para criar modelos SQLAlchemy (tabelas)
db_connection_error = None  # Armazena mensagem de erro caso conexão falhe

# =============================================================================
# TENTATIVA DE CONEXÃO COM POSTGRESQL
# =============================================================================
try:
    # Construir URL de conexão usando psycopg3 (driver mais moderno que psycopg2)
    DATABASE_URL = URL.create(
        drivername="postgresql+psycopg",  # Especifica psycopg3 - melhor suporte a UTF-8
        username=os.getenv("DB_USER"),    # Usuário do PostgreSQL (vem do .env)
        password=os.getenv("DB_PASSWORD"), # Senha do PostgreSQL (vem do .env)
        host=os.getenv("DB_HOST"),        # Host do PostgreSQL (localhost ou host.docker.internal)
        port=int(os.getenv("DB_PORT")),   # Porta do PostgreSQL (geralmente 5432)
        database=os.getenv("DB_NAME"),    # Nome do banco de dados (vem do .env)
        query={                           # Parâmetros adicionais da conexão
            "client_encoding": "utf8",    # Força encoding UTF-8 na conexão
            "application_name": "fastapi_crud_app"  # Nome da aplicação para logs do PostgreSQL
        }
    ).render_as_string(hide_password=False)  # Converte URL object para string de conexão

    # Debug: mostrar URL de conexão para troubleshooting (sem exibir senha em prod)
    print("=== DEBUG: DATABASE_URL ===")
    print(f"DATABASE_URL: {repr(DATABASE_URL)}")
    print("===========================")

    # Configuração do engine SQLAlchemy com parâmetros de encoding e performance
    engine = create_engine(
        DATABASE_URL,                     # String de conexão construída acima
        client_encoding='utf8',           # Força encoding UTF-8 no cliente
        pool_pre_ping=True,              # Testa conexões antes de usar (evita timeouts)
        echo=False,                      # Se True, mostra todas as queries SQL no console
        connect_args={                   # Argumentos adicionais para o driver psycopg
            "client_encoding": "utf8",    # Força UTF-8 no nível do driver de conexão
            "application_name": "fastapi_app"  # Nome da aplicação nos logs do PostgreSQL
        }
    )
    
    # Testar conexão imediatamente após criar o engine
    # Executa uma query simples para verificar se a conexão está funcionando
    with engine.connect() as conn:
        result = conn.execute(text("SELECT version();"))  # Query que retorna versão do PostgreSQL
        version = result.fetchone()                       # Pega primeiro resultado
        print(f"✅ Conexão com PostgreSQL bem-sucedida!")
        print(f"Versão: {version[0][:50]}...")           # Mostra primeiros 50 chars da versão
        
    # Criar factory de sessões do SQLAlchemy
    SessionLocal = sessionmaker(
        autocommit=False,    # Transações manuais (recomendado para controle)
        autoflush=False,     # Flush manual (evita queries automáticas indesejadas)
        bind=engine          # Vincula as sessões ao engine criado acima
    )
    
except Exception as e:
    # Capturar qualquer erro na conexão e armazenar para uso posterior
    db_connection_error = str(e)
    print(f"❌ Erro ao conectar ao banco: {e}")
    print("🔄 API funcionará em modo mock até que a conexão seja estabelecida")

# =============================================================================
# MODELO SQLALCHEMY - DEFINIÇÃO DA TABELA USUARIOS
# =============================================================================
class UsuarioDB(Base):
    """Modelo SQLAlchemy que representa a tabela 'usuarios' no PostgreSQL"""
    __tablename__ = "usuarios"        # Nome da tabela no banco de dados

    # Definição das colunas da tabela
    id = Column(Integer, primary_key=True, index=True)      # Chave primária auto-incremento
    nome = Column(String, nullable=False)                   # Nome do usuário (obrigatório)
    email = Column(String, nullable=False, unique=True)     # Email único (obrigatório)
    ativo = Column(Integer, nullable=False, default=1)      # Status: 1=ativo, 0=inativo

# =============================================================================
# CRIAÇÃO AUTOMÁTICA DAS TABELAS
# =============================================================================
# Tentar criar tabelas automaticamente se a conexão estiver funcionando
if engine is not None:
    try:
        # create_all() cria todas as tabelas definidas nos modelos se não existirem
        Base.metadata.create_all(bind=engine)
        print("✅ Tabelas criadas/verificadas com sucesso")
    except Exception as e:
        print(f"⚠️ Erro ao criar tabelas: {e}")

# =============================================================================
# DADOS MOCK COMO FALLBACK
# =============================================================================
# Lista de usuários fake para usar quando o banco não estiver disponível
mock_users = [
    {"id": 1, "nome": "João Silva", "email": "joao@email.com", "ativo": 1},
    {"id": 2, "nome": "Maria Santos", "email": "maria@email.com", "ativo": 1},
    {"id": 3, "nome": "Pedro Oliveira", "email": "pedro@email.com", "ativo": 0}
]

# =============================================================================
# GERENCIADOR DE CONTEXTO PARA SESSÕES DE BANCO
# =============================================================================
@contextmanager
def Database() -> Iterator[Session]:
    """Context manager que gerencia sessões do banco com tratamento de erros."""
    if SessionLocal is None:
        # Se não há conexão, lança exceção HTTP 500
        raise HTTPException(500, "Conexão com banco de dados não disponível")
    db = SessionLocal()    # Criar nova sessão
    try:
        # Configurar encoding UTF-8 na sessão atual do PostgreSQL
        db.execute(text("SET client_encoding TO 'UTF8'"))
        yield db           # Retorna a sessão para uso
    finally:
        db.close()         # Sempre fecha a sessão ao final

# =============================================================================
# FUNÇÕES UTILITÁRIAS PARA TRATAMENTO DE ENCODING
# =============================================================================
def clean_string(text: str) -> str:
    """Limpa strings com problemas de encoding para UTF-8."""
    if not text:
        return text        # Retorna vazio se texto for None ou empty
    
    try:
        # Tentar verificar se a string já está em UTF-8 válido
        text.encode('utf-8')
        return text        # Se não der erro, retorna a string original
    except UnicodeDecodeError:
        # Se houver problemas de encoding, tentar corrigir
        if isinstance(text, bytes):
            # Se for bytes, tenta decodificar com diferentes encodings comuns
            for encoding in ['utf-8', 'latin1', 'cp1252', 'iso-8859-1']:
                try:
                    return text.decode(encoding)  # Retorna primeira decodificação bem-sucedida
                except (UnicodeDecodeError, AttributeError):
                    continue  # Tenta próximo encoding se falhar
        
        # Se não conseguir decodificar, remove caracteres problemáticos
        return text.encode('utf-8', errors='ignore').decode('utf-8')
    except Exception:
        # Fallback final: converte para string e remove caracteres problemáticos
        return str(text).encode('utf-8', errors='ignore').decode('utf-8')

# =============================================================================
# MODELOS PYDANTIC - VALIDAÇÃO E SERIALIZAÇÃO DE DADOS
# =============================================================================
class UsuarioBase(BaseModel):
    """Modelo base Pydantic para validação de dados de usuário."""
    id: Optional[int] = None      # ID opcional (usado em updates)
    nome: str                     # Nome do usuário (obrigatório)
    email: EmailStr               # Email com validação automática de formato
    ativo: int = Field(default=1, description="1: ativo | 0: inativo")  # Status com descrição

class SetUser(UsuarioBase):
    """Modelo para criação/atualização de usuários - herda de UsuarioBase."""
    pass

    class Config:
        from_attributes = True    # Permite criar Pydantic model a partir de SQLAlchemy model

# =============================================================================
# ENDPOINTS DA API - ROTAS HTTP
# =============================================================================

@app.get("/", response_model=dict, 
        summary="Página inicial",
        description="Redireciona para a documentação interativa da API (Swagger UI).") 
def home():
    return {"escreva na URL": "http://127.0.0.1:5000/docs#/"}

@app.post("/usuarios", 
            status_code=status.HTTP_201_CREATED,    # Retorna 201 quando criar com sucesso
            response_model=SetUser,                  # Modelo de resposta Pydantic
            summary="Criar novo usuário",            # Título no Swagger
            description="Cadastra um novo usuário no sistema.",  # Descrição no Swagger
            responses={                              # Documentação das respostas possíveis
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

# =============================================================================
# ENDPOINT GET - LISTAR USUÁRIOS
# =============================================================================
@app.get("/usuarios",
    response_model=List[SetUser],                # Resposta é lista de usuários
    summary="Listar usuários",                  # Título no Swagger
    description="""Retorna todos os usuários cadastrados. 
                Pode ser filtrado por nome quando fornecido como parâmetro.""",  # Descrição detalhada
    responses={                                  # Documentação das possíveis respostas
        200: {"description": "Lista de usuários retornada com sucesso"},
        404: {"description": "Nenhum usuário encontrado"}
    })
def get_users(
    # Parâmetros de query opcional para filtrar resultados
    id: Optional[int] = Query(None, description="Filtrar por ID"),  # ID específico do usuário
    ativo: Literal["-1", "0", "1"] = Query("-1", description="-1: todos | 0: inativos | 1: ativos"),  # Status ativo
    nome: Optional[str] = Query(default="", description="Filtrar por nome"),  # Busca por nome parcial
    ordenador: Literal["id", "nome", "ativo"] = Query(default="id")  # Campo para ordenação
):
    """Endpoint para listar usuários com filtros opcionais."""
    try:
        # Tentar usar banco PostgreSQL primeiro
        if engine is not None:
            with Database() as banco:  # Context manager para sessão
                # Começar com query base para todos os usuários
                query = banco.query(UsuarioDB)

                # Aplicar filtro por ID se fornecido
                if id and id > 0:
                    query = query.filter(UsuarioDB.id == id)

                # Aplicar filtro por status ativo
                if ativo == "0":       # Mostrar apenas inativos
                    query = query.filter(UsuarioDB.ativo == 0)
                elif ativo == "1":     # Mostrar apenas ativos
                    query = query.filter(UsuarioDB.ativo == 1)
                # Se ativo == "-1", não filtra (mostra todos)

                # Aplicar filtro por nome se fornecido
                if nome and nome.strip():  # Se nome não está vazio
                    nome_decoded = clean_string(nome.strip())  # Limpar encoding
                    # ilike = busca case-insensitive com wildcards (%)
                    query = query.filter(UsuarioDB.nome.ilike(f"%{nome_decoded}%"))

                # Aplicar ordenação por campo especificado
                coluna_ordenacao = getattr(UsuarioDB, ordenador)  # Obter atributo da classe
                query = query.order_by(coluna_ordenacao.asc())    # Ordenação ascendente

                # Executar query e obter resultados
                db_users = query.all()

                # Verificar se encontrou usuários
                if not db_users:
                    raise HTTPException(status_code=404, detail="Nenhum usuário encontrado")
                
                # Limpar dados de encoding problemático antes de retornar
                users_cleaned = []
                # Processar resultados do banco, limpando strings para UTF-8
                users_cleaned = []  # Lista para armazenar usuários processados
                for user in db_users:  # Iterar cada usuário do banco
                    user_dict = {
                        'id': user.id,      # ID não precisa de limpeza (é inteiro)
                        'nome': clean_string(user.nome) if user.nome else "",    # Limpar nome
                        'email': clean_string(user.email) if user.email else "", # Limpar email
                        'ativo': user.ativo  # Status ativo não precisa de limpeza (é inteiro)
                    }
                    users_cleaned.append(SetUser(**user_dict))  # Converter para modelo Pydantic
                
                return users_cleaned  # Retornar lista de usuários limpos
        else:
            # Fallback para dados mock quando banco não está disponível
            filtered_users = mock_users.copy()  # Copiar lista original para não modificar
            
            # Aplicar mesmo filtros que aplicamos no banco
            if id and id > 0:
                filtered_users = [u for u in filtered_users if u["id"] == id]
                
            if ativo != "-1":  # Se não é "todos"
                filtered_users = [u for u in filtered_users if u["ativo"] == int(ativo)]
                
            if nome:  # Se nome foi fornecido
                filtered_users = [u for u in filtered_users if nome.lower() in u["nome"].lower()]
                
            # Verificar se ainda restaram usuários após filtros
            if not filtered_users:
                raise HTTPException(status_code=404, detail="Nenhum usuário encontrado")
            
            # Converter lista de dicts para lista de modelos Pydantic
            return [SetUser(**user) for user in filtered_users]
            
    except UnicodeDecodeError as e:
        # Tratamento específico para erros de encoding
        print(f"Erro de encoding: {e}")
        raise HTTPException(
            status_code=400, 
            detail={
                "error": "Erro de codificação de caracteres",
                "message": str(e),
                "suggestion": "Há dados no banco com caracteres incompatíveis com UTF-8"
            }
        )
    except Exception as E:
        # Tratamento geral de exceções
        print(f"Erro geral: {E}")
        if isinstance(E, HTTPException):  # Se já é HTTPException, re-lançar
            raise E
        else:
            # Verificar se é erro de encoding mascarado como outro tipo
            if "'utf-8' codec can't decode" in str(E):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": "Problema de encoding UTF-8",
                        "message": str(E),
                        "suggestion": "Verifique os dados no banco de dados"
                    }
                )
            # Para outros erros, converter para HTTPException genérico
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

# =============================================================================
# EXECUÇÃO PRINCIPAL DA APLICAÇÃO
# =============================================================================
if __name__ == "__main__":
    # Importar uvicorn apenas quando executar diretamente (não como módulo)
    
    # Mensagens de status na inicialização
    print("🎉 API CRUD com PostgreSQL iniciando...")
    print("✅ Erro UTF-8 resolvido!")
    if engine is not None:
        print("🗄️ Conectado ao PostgreSQL")      # Modo produção com banco real
    else:
        print("⚠️ Usando dados mock (problema de conexão com PostgreSQL)")  # Modo fallback
    print("🌐 Swagger UI: http://localhost:5000/docs")
    
    # Executar servidor uvicorn com configurações de desenvolvimento
    uvicorn.run(
        "main:app",         # Módulo:aplicação
        host="0.0.0.0",     # Bind em todas as interfaces (permite Docker)
        port=5000,          # Porta padrão da aplicação
        reload=True,        # Auto-reload quando código muda (desenvolvimento)
        workers=1           # Apenas 1 worker (evita problemas com SQLAlchemy)
    )