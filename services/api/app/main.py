"""API do VagaCerta — MVP com dados mockados.

Rodar:  .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
Docs:   http://localhost:8000/docs
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import mapeamento, parceiros, uso, vagas
from app.config import CORS_ORIGENS, DISTANCIA_MAXIMA_M, Relogio
from app.erros import ErroNegocio
from app.estado import Estado


def criar_app(relogio: Relogio | None = None, semear: bool = True,
              distancia_maxima_m: float = DISTANCIA_MAXIMA_M) -> FastAPI:
    app = FastAPI(
        title="VagaCerta API",
        description="MVP acadêmico — Centro com dados de demonstração, Batel com dados reais "
                    "(OpenStreetMap, IPPUC e Setran). Pagamentos simulados.",
        version="0.1.0",
    )
    app.state.estado = Estado.criar(relogio=relogio, semear=semear, distancia_maxima_m=distancia_maxima_m)
    app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGENS, allow_methods=["*"], allow_headers=["*"])

    @app.exception_handler(ErroNegocio)
    def _erro_negocio(_: Request, erro: ErroNegocio):
        return JSONResponse(status_code=erro.status, content={"detail": erro.mensagem})

    @app.get("/saude", tags=["infra"])
    def saude():
        return {"status": "ok", "agora": app.state.estado.relogio().isoformat(),
                "distancia_maxima_m": distancia_maxima_m}

    app.include_router(vagas.router)
    app.include_router(uso.router)
    app.include_router(parceiros.router)
    app.include_router(mapeamento.router)
    return app


app = criar_app()
