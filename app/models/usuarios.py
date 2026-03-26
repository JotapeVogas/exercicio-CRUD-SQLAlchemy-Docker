from sqlalchemy import BigInteger, PrimaryKeyConstraint, String, Integer, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base

class UsuarioDB(Base):
    __tablename__ = 'usuarios'
    __table_args__ = (
        PrimaryKeyConstraint('id_usuario', name='usuarios_pkey'),
    )

    id_usuario: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nome: Mapped[str] = mapped_column(String(255))
    ativo: Mapped[int] = mapped_column(Integer, server_default=text('1'))
