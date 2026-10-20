// Cliente da API do VagaCerta para o painel do parceiro.
// A URL vem de NEXT_PUBLIC_API_URL (ver .env.example); por padrão, a API local.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

export interface Parceiro {
  id: string;
  nome: string;
}

export interface EstadoVaga {
  prob_livre: number;
  vagas_livres_estimadas: number;
  confianca: number;
  fonte: string;
  atualizado_ha_min: number | null;
  ao_vivo: boolean;
  nivel: "facil" | "moderado" | "dificil";
  explicacao: string | null;
  rotulo: string;
}

export interface Reserva {
  id: string;
  codigo: string;
  expira_em: string;
  status: string;
}

export interface EstacionamentoNoPainel {
  estacionamento: {
    id: string;
    nome: string;
    endereco: string;
    capacidade: number;
    preco_hora: number;
    aceita_reserva: boolean;
    cota_reserva: number;
  };
  estado: EstadoVaga;
  reservas_ativas: Reserva[];
  cota_reserva_disponivel: number;
}

export interface Metricas {
  chegadas_avaliadas: number;
  acertos: number;
  taxa_acerto: number | null;
}

async function chamar<T>(caminho: string, init: RequestInit = {}): Promise<T> {
  let resposta: Response;
  try {
    resposta = await fetch(`${API_URL}${caminho}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init.headers },
      cache: "no-store",
    });
  } catch {
    throw new Error(`Não consegui falar com a API em ${API_URL}. Ela está rodando?`);
  }
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null);
    throw new Error(typeof corpo?.detail === "string" ? corpo.detail : `Erro ${resposta.status}`);
  }
  return resposta.json();
}

export const api = {
  parceiros: () => chamar<Parceiro[]>("/parceiros"),
  estacionamentos: (parceiroId: string) =>
    chamar<EstacionamentoNoPainel[]>(`/parceiros/${parceiroId}/estacionamentos`),
  atualizarOcupacao: (parceiroId: string, estacionamentoId: string, vagas_livres: number) =>
    chamar<EstacionamentoNoPainel>(`/parceiros/${parceiroId}/estacionamentos/${estacionamentoId}/ocupacao`, {
      method: "PUT",
      body: JSON.stringify({ vagas_livres }),
    }),
  metricas: () => chamar<Metricas>("/metricas"),
};
