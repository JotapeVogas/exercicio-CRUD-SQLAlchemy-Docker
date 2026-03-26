from fastapi import FastAPI
from app.database.connection import engine
from app.database.base import Base
import app.models.usuarios # Garante que as tabelas sejam criadas
Base.metadata.create_all(bind=engine)

app = FastAPI()

# Rotas
@app.get('/', response_model=dict,
        summary='Página inicial',
        description='Redireciona para a documentação interativa da API (Swagger UI).')
def home():
    return {'escreva na URL': 'http://127.0.0.1:5000/docs#/'}

from app.api.v1.endpoints import usuarios
app.include_router(usuarios.router, prefix='/usuarios', tags=['Usuários'])      

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        'app.main:app',
        host='127.0.0.1',
        port=5000,
        reload=True,
        workers=1
    )


