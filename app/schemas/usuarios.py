from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict

class ListUsuarios(BaseModel):
    class Usuario(BaseModel):
        id_usuario: int = Field(0)
        nome: Optional[str] = Field('')
        ativo: int = Field(1)
        
        model_config = ConfigDict(from_attributes=True)

    usuarios: List[Usuario] = Field([], examples=[[Usuario()]])

class Setusuario(BaseModel):
    id_usuario: Optional[int] = Field(None, examples=[-1])
    nome: Optional[str] = Field('')
    ativo: int = Field(1)

    model_config = ConfigDict(from_attributes=True)

class Editusuario(Setusuario):
    id_usuario: int = Field()
