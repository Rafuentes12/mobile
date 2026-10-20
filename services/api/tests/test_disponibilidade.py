from datetime import timedelta

from app.catalogo import CatalogoArquivos
from app.servicos.disponibilidade import ServicoDisponibilidade, Sinal
from tests.conftest import TERCA_10H30 as AGORA


def servico() -> ServicoDisponibilidade:
    return ServicoDisponibilidade(CatalogoArquivos())


def test_sem_sinais_usa_o_modelo_e_nao_mostra_porcentagem():
    estado = servico().estado("t-02", AGORA)
    assert estado.fonte == "modelo" and not estado.ao_vivo
    assert estado.rotulo in ("Fácil (estimativa)", "Moderado (estimativa)", "Difícil (estimativa)")
    assert "%" not in estado.rotulo
    assert estado.explicacao.startswith("Terça, 10h")
    assert estado.atualizado_ha_min is None


def test_sinal_recente_domina_e_mostra_fonte_e_idade():
    s = servico()
    s.registrar(Sinal(alvo_id="est-01", fonte="atendente", criado_em=AGORA - timedelta(minutes=2), vagas_livres=12))
    estado = s.estado("est-01", AGORA)
    assert estado.fonte == "atendente"
    assert estado.vagas_livres_estimadas == 12
    assert estado.rotulo == "12 vagas · atendente · há 2 min"
    assert estado.ao_vivo


def test_reporte_de_usuario_perde_forca_em_minutos():
    s = servico()
    s.registrar(Sinal(alvo_id="t-01", fonte="usuario", criado_em=AGORA, livre=True))
    assert s.estado("t-01", AGORA).fonte == "usuario"
    assert s.estado("t-01", AGORA + timedelta(minutes=10)).fonte == "modelo"


def test_estacionamento_lotado():
    s = servico()
    s.registrar(Sinal(alvo_id="est-02", fonte="cancela", criado_em=AGORA, vagas_livres=0))
    estado = s.estado("est-02", AGORA)
    assert estado.prob_livre < 0.5
    assert estado.rotulo.startswith("Lotado")


def test_previsao_para_a_chegada_considera_o_envelhecimento_do_sinal():
    s = servico()
    s.registrar(Sinal(alvo_id="est-01", fonte="atendente", criado_em=AGORA, vagas_livres=12))
    agora = s.estado("est-01", AGORA)
    daqui_40_min = s.estado("est-01", AGORA, momento=AGORA + timedelta(minutes=40))
    assert daqui_40_min.confianca < agora.confianca
