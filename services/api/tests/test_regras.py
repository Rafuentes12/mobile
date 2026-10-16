from datetime import datetime

from app.catalogo import CatalogoMock
from app.config import FUSO
from app.servicos.regras import avaliar_rua, estacionamento_aberto, preco_estacionamento

catalogo = CatalogoMock()
centro = catalogo.setor("centro")
area_calma = catalogo.setor("centro-area-calma")


def em(dia: int, hora: int, minuto: int = 0) -> datetime:
    return datetime(2026, 10, dia, hora, minuto, tzinfo=FUSO)  # 20/10/2026 = terça


def test_permanencia_maior_que_o_limite_do_estar_e_bloqueada():
    avaliacao = avaliar_rua(centro, em(20, 10, 30), 180)
    assert not avaliacao.permitido
    assert "2 h" in avaliacao.motivo


def test_limite_conta_so_o_tempo_dentro_do_horario_de_cobranca():
    avaliacao = avaliar_rua(centro, em(20, 17, 30), 180)  # cobrança termina às 19h → 90 min cobrados
    assert avaliacao.permitido
    assert avaliacao.minutos_cobrados == 90
    assert avaliacao.preco == 6.0  # 6 frações de 15 min × R$ 1,00 (valor fictício)


def test_domingo_e_gratis():
    avaliacao = avaliar_rua(centro, em(25, 11), 240)
    assert avaliacao.permitido and avaliacao.preco == 0


def test_area_calma_tem_limite_de_uma_hora():
    assert not avaliar_rua(area_calma, em(20, 10), 90).permitido
    assert avaliar_rua(area_calma, em(20, 10), 60).permitido


def test_horario_e_preco_de_estacionamento():
    est = catalogo.estacionamento("est-01")
    assert estacionamento_aberto(est, em(20, 10))
    assert not estacionamento_aberto(est, em(25, 10))  # fechado no domingo
    assert preco_estacionamento(est, 90) == 24.0      # 2 h × R$ 12
    assert preco_estacionamento(est, 600) == 45.0     # limitado à diária
