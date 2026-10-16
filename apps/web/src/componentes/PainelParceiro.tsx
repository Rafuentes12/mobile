"use client";

import { useEffect, useState } from "react";

import { api, type EstacionamentoNoPainel, type Metricas, type Parceiro } from "@/lib/api";

const INTERVALO_ATUALIZACAO_MS = 15_000;

function horaCurta(iso: string) {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function classeDoEstado(prob: number) {
  if (prob >= 0.7) return "livre";
  if (prob >= 0.4) return "talvez";
  return "ocupada";
}

export function PainelParceiro() {
  const [parceiros, setParceiros] = useState<Parceiro[]>([]);
  const [parceiroId, setParceiroId] = useState<string>("");
  const [itens, setItens] = useState<EstacionamentoNoPainel[]>([]);
  const [metricas, setMetricas] = useState<Metricas | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    api
      .parceiros()
      .then((lista) => {
        setParceiros(lista);
        setParceiroId((atual) => atual || lista[0]?.id || "");
      })
      .catch((e: Error) => setErro(e.message));
  }, []);

  useEffect(() => {
    if (!parceiroId) return;
    let ativo = true;
    const carregar = () =>
      Promise.all([api.estacionamentos(parceiroId), api.metricas()])
        .then(([lista, m]) => {
          if (!ativo) return;
          setItens(lista);
          setMetricas(m);
          setErro(null);
        })
        .catch((e: Error) => ativo && setErro(e.message));
    carregar();
    const id = setInterval(carregar, INTERVALO_ATUALIZACAO_MS);
    return () => {
      ativo = false;
      clearInterval(id);
    };
  }, [parceiroId]);

  async function atualizar(estacionamentoId: string, vagas: number) {
    try {
      const atualizado = await api.atualizarOcupacao(parceiroId, estacionamentoId, vagas);
      setItens((lista) => lista.map((i) => (i.estacionamento.id === estacionamentoId ? atualizado : i)));
      setErro(null);
    } catch (e) {
      setErro((e as Error).message);
    }
  }

  return (
    <section className="painel">
      <div className="barra">
        <label>
          Parceiro{" "}
          <select value={parceiroId} onChange={(e) => setParceiroId(e.target.value)}>
            {parceiros.map((p) => (
              <option key={p.id} value={p.id}>
                {p.nome}
              </option>
            ))}
          </select>
        </label>
        {metricas && (
          <span className="metrica">
            Taxa de acerto do app:{" "}
            <strong>
              {metricas.taxa_acerto === null ? "sem dados" : `${Math.round(metricas.taxa_acerto * 100)}%`}
            </strong>{" "}
            ({metricas.chegadas_avaliadas} chegadas avaliadas)
          </span>
        )}
      </div>

      {erro && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}

      <div className="cartoes">
        {itens.map((item) => (
          <CartaoEstacionamento key={item.estacionamento.id} item={item} onAtualizar={atualizar} />
        ))}
      </div>
    </section>
  );
}

function CartaoEstacionamento({
  item,
  onAtualizar,
}: {
  item: EstacionamentoNoPainel;
  onAtualizar: (id: string, vagas: number) => Promise<void>;
}) {
  const { estacionamento: est, estado, reservas_ativas, cota_reserva_disponivel } = item;
  const [vagas, setVagas] = useState(estado.vagas_livres_estimadas);
  const [salvando, setSalvando] = useState(false);

  async function salvar(valor: number) {
    const ajustado = Math.max(0, Math.min(est.capacidade, valor));
    setVagas(ajustado);
    setSalvando(true);
    await onAtualizar(est.id, ajustado);
    setSalvando(false);
  }

  return (
    <article className="cartao">
      <header>
        <h2>{est.nome}</h2>
        <p className="suave">
          {est.endereco} · {est.capacidade} vagas · R$ {est.preco_hora.toFixed(2).replace(".", ",")}/h
        </p>
      </header>

      <p className={`estado ${classeDoEstado(estado.prob_livre)}`}>{estado.rotulo}</p>

      <div className="controle">
        <span>Vagas livres agora</span>
        <div className="contador">
          <button type="button" onClick={() => salvar(vagas - 1)} disabled={salvando} aria-label="Uma vaga a menos">
            −
          </button>
          <input
            type="number"
            min={0}
            max={est.capacidade}
            value={vagas}
            onChange={(e) => setVagas(Number(e.target.value))}
            aria-label="Vagas livres"
          />
          <button type="button" onClick={() => salvar(vagas + 1)} disabled={salvando} aria-label="Uma vaga a mais">
            +
          </button>
        </div>
        <div className="acoes">
          <button type="button" className="principal" onClick={() => salvar(vagas)} disabled={salvando}>
            Informar
          </button>
          <button type="button" onClick={() => salvar(0)} disabled={salvando}>
            Lotado
          </button>
        </div>
      </div>

      {est.aceita_reserva ? (
        <div className="reservas">
          <p className="suave">
            Reservas VagaCerta: {reservas_ativas.length} ativa(s) · {cota_reserva_disponivel} de {est.cota_reserva}{" "}
            disponíveis na cota
          </p>
          {reservas_ativas.length > 0 && (
            <ul>
              {reservas_ativas.map((r) => (
                <li key={r.id}>
                  <code>{r.codigo}</code> · expira às {horaCurta(r.expira_em)}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <p className="suave">Não aceita reservas (sem integração com a cancela).</p>
      )}
    </article>
  );
}
