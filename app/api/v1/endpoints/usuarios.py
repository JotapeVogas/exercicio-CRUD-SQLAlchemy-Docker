import json
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, Path
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database.connection import get_session
from app.models.usuarios import UsuarioDB
from app.schemas.usuarios import ListUsuarios, Setusuario, Editusuario

class UsuariosRouter(APIRouter):
    def __init__(self):
        super().__init__()

        self.add_api_route('',
                           self.get_usuarios,
                           methods=['GET'],
                           response_model=ListUsuarios,
                           summary="Listar usuários",
                           description="Retorna todos os usuários cadastrados. Pode ser filtrado por nome.",
                           responses={
                               200: {"description": "Lista de usuários retornada com sucesso"},
                               404: {"description": "Nenhum usuário encontrado"}
                           })
        
        self.add_api_route('',
                           self.set_usuario,
                           methods=['POST'],
                           status_code=status.HTTP_201_CREATED,
                           response_model=Setusuario,
                           summary="Criar novo usuário",
                           description="Cadastra um novo usuário no sistema.",
                           responses={
                               201: {"description": "Usuário criado com sucesso"},
                               400: {"description": "Dados inválidos ou erro no banco de dados"}
                           })
        
        self.add_api_route('',
                           self.update_usuario,
                           methods=['PATCH'],
                           response_model=Editusuario,
                           summary="Atualizar usuário",
                           description="Atualiza os dados de um usuário existente pelo seu ID.",
                           responses={
                               200: {"description": "Usuário atualizado com sucesso"},
                               400: {"description": "Dados inválidos"},
                               404: {"description": "Usuário não encontrado"}
                           })
        
        self.add_api_route('/{id_usuario}/ativar',
                           self.activate_usuario,
                           methods=['PATCH'],
                           summary="Ativar usuário",
                           description="Ativa um usuário pelo seu ID.",
                           responses={
                               200: {"description": "Usuário atualizado com sucesso"},
                               400: {"description": "Dados inválidos"},
                               404: {"description": "Usuário não encontrado"}
                           })
        
        self.add_api_route('/{id_usuario}',
                           self.delete_usuario,
                           methods=['DELETE'],
                           status_code=status.HTTP_200_OK,
                           summary="Desativar usuário",
                           description="Exclui logicamente um usuário do sistema pelo seu ID.",
                           responses={
                               200: {"description": "Usuário removido com sucesso"},
                               404: {"description": "Usuário não encontrado"},
                               500: {"description": "Erro interno no servidor"}
                           })

    def get_usuarios(self,
        banco: Session = Depends(get_session),
        id: Optional[int] = Query(None, description="Filtrar por ID"),
        ativo: Literal["-1", "0", "1"] = Query("-1", description="-1: todos | 0: inativos | 1: ativos"),
        nome: Optional[str] = Query(default="", description="Filtrar por nome"),
        ordenador: Literal["id_usuario", "nome", "ativo"] = Query(default="id_usuario")
    ):
        try:
            model_list_usuarios = ListUsuarios.model_construct()
            
            db_usuarios = banco.query(UsuarioDB).filter(
                UsuarioDB.nome.ilike(f"%{nome.strip()}%") if nome else True,
                UsuarioDB.id_usuario == id if id is not None else True,
                UsuarioDB.ativo.in_([0, 1]) if ativo == "-1" else UsuarioDB.ativo == int(ativo),
            ).order_by(getattr(UsuarioDB, ordenador)).all()

            if db_usuarios:
                model_list_usuarios.usuarios = [ListUsuarios.Usuario.model_construct(
                ).model_validate(usuario, from_attributes=True) for usuario in db_usuarios]

            return JSONResponse(json.loads(model_list_usuarios.model_dump_json()), 200)
        except Exception as E:
            if isinstance(E, HTTPException):
                raise E
            else:
                raise HTTPException(400, str(E))

    def set_usuario(self, usuario_info: Setusuario = Body(...), banco: Session = Depends(get_session)):
        try:
            db_usuario = UsuarioDB(**usuario_info.model_dump(exclude={"id_usuario"}))
            
            banco.add(db_usuario)
            banco.flush()
            banco.refresh(db_usuario)
            
            if db_usuario.id_usuario:
                usuario_info.id_usuario = db_usuario.id_usuario
                
            return JSONResponse(json.loads(usuario_info.model_dump_json()), 201)
        except Exception as E:
            if isinstance(E, HTTPException):
                raise E
            else:
                raise HTTPException(400, str(E))

    def update_usuario(self, usuario_info: Editusuario = Body(..., title="Dados do usuário para atualização"), banco: Session = Depends(get_session)):
        try:
            db_usuario = banco.query(UsuarioDB).filter(
                UsuarioDB.id_usuario == usuario_info.id_usuario
            ).update(
                usuario_info.model_dump(exclude_unset=True, exclude={"id_usuario"})
            )
            if not db_usuario:
                raise HTTPException(404, 'Usuário não encontrado!')
                
            return JSONResponse({"detail": "success"}, 200)
        except Exception as E:
            if isinstance(E, HTTPException):
                raise E
            else:
                raise HTTPException(400, str(E))

    def activate_usuario(self, id_usuario: int = Path(..., title="ID do usuário", description="ID do usuário a ser ativado"), banco: Session = Depends(get_session)):
        try:
            db_usuario = banco.query(UsuarioDB).filter(
                UsuarioDB.id_usuario == id_usuario
            ).update(
                {"ativo": 1}
            )
            if not db_usuario:
                raise HTTPException(404, 'Usuário não encontrado!')
            
            return JSONResponse({"detail": "success"}, 200)
        except Exception as E:
            if isinstance(E, HTTPException):
                raise E
            else:
                raise HTTPException(400, str(E))

    def delete_usuario(self, id_usuario: int = Path(..., title="ID do usuário", description="ID do usuário a ser removido"), banco: Session = Depends(get_session)):
        try:
            db_usuario = banco.query(UsuarioDB).filter(
                UsuarioDB.id_usuario == id_usuario
            ).update(
                {"ativo": 0}
            )
            if not db_usuario:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Usuário não encontrado"
                )
            
            return JSONResponse({"detail": "success"}, 200)
        except Exception as E:
            if isinstance(E, HTTPException):
                raise E
            else:
                raise HTTPException(400, str(E))

router = UsuariosRouter()

