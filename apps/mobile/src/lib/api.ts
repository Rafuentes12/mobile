import Constants from 'expo-constants';

import type {
  Contexto,
  Coordenada,
  Credencial,
  Destino,
  Reserva,
  RespostaRecomendacao,
  ResultadoMapeamento,
  ResultadoSugestao,
  Sessao,
  VagaNoMapa,
} from './tipos';

// No celular, "localhost" é o próprio celular. Por padrão usamos o IP do computador
// que roda o `expo start` (o mesmo onde a API deve estar rodando na porta 8000).
function resolverUrlDaApi(): string {
  const definida = process.env.EXPO_PUBLIC_API_URL;
  if (definida) return definida.replace(/\/$/, '');
  const host = Constants.expoConfig?.hostUri?.split(':')[0];
  return host ? `http://${host}:8000` : 'http://localhost:8000';
}

export const API_URL = resolverUrlDaApi();

// Sem login no MVP: cada abertura do app vira um usuário de teste diferente.
const USUARIO_ID = `demo-${Math.random().toString(36).slice(2, 8)}`;

async function chamar<T>(caminho: string, init: RequestInit = {}): Promise<T> {
  let resposta: Response;
  try {
    resposta = await fetch(`${API_URL}${caminho}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', 'X-Usuario-Id': USUARIO_ID, ...init.headers },
    });
  } catch {
    throw new Error(`Não consegui falar com a API em ${API_URL}. Ela está rodando?`);
  }
  if (!resposta.ok) {
    const corpo = await resposta.json().catch(() => null);
    const detalhe = typeof corpo?.detail === 'string' ? corpo.detail : `Erro ${resposta.status}`;
    throw new Error(detalhe);
  }
  return resposta.status === 204 ? (undefined as T) : resposta.json();
}

function consulta(params: Record<string, string | number | undefined>): string {
  const pares = Object.entries(params).filter(([, v]) => v !== undefined) as [string, string | number][];
  return new URLSearchParams(pares.map(([k, v]) => [k, String(v)])).toString();
}

const post = <T>(caminho: string, corpo?: unknown) =>
  chamar<T>(caminho, { method: 'POST', body: corpo === undefined ? undefined : JSON.stringify(corpo) });

export const api = {
  saude: () => chamar<{ status: string; distancia_maxima_m: number }>('/saude'),

  destinos: (q: string) => chamar<Destino[]>(`/destinos?${consulta({ q })}`),

  vagas: (lat: number, lng: number, raio_m: number) =>
    chamar<VagaNoMapa[]>(`/vagas?${consulta({ lat, lng, raio_m })}`),

  recomendacoes: (p: {
    destino: Destino;
    contexto: Contexto;
    duracao_min: number;
    credencial: Credencial;
    origem?: { lat: number; lng: number } | null;
  }) =>
    chamar<RespostaRecomendacao>(
      `/recomendacoes?${consulta({
        lat: p.destino.lat,
        lng: p.destino.lng,
        contexto: p.contexto,
        duracao_min: p.duracao_min,
        credencial: p.credencial,
        origem_lat: p.origem?.lat,
        origem_lng: p.origem?.lng,
      })}`,
    ),

  reservar: (estacionamento_id: string) => post<Reserva>('/reservas', { estacionamento_id }),
  cancelarReserva: (id: string) => post<Reserva>(`/reservas/${id}/cancelar`),

  // A API exige a posição atual: só dá para iniciar perto da vaga.
  iniciarSessao: (alvo_id: string, placa: string, duracao_min: number, posicao: Coordenada) =>
    post<Sessao>('/sessoes', { alvo_id, placa, duracao_min, ...posicao }),
  estenderSessao: (id: string, minutos: number) => post<Sessao>(`/sessoes/${id}/estender`, { minutos }),
  encerrarSessao: (id: string) => post<Sessao>(`/sessoes/${id}/encerrar`),

  reportar: (alvo_id: string, livre: boolean, posicao: Coordenada) =>
    post<void>('/reportes', { alvo_id, livre, ...posicao }),
  avaliarChegada: (alvo_id: string, encontrou: boolean) => post<unknown>('/chegadas', { alvo_id, encontrou }),

  // Mapeamento colaborativo (todas as ações exigem estar perto do local).
  mapearTrecho: (trecho_id: string, tipo: 'tem_estar' | 'sem_estar' | 'proibido', posicao: Coordenada) =>
    post<ResultadoMapeamento>(`/mapeamento/trechos/${trecho_id}`, { tipo, ...posicao }),
  informarFechado: (estacionamento_id: string, posicao: Coordenada) =>
    post<ResultadoMapeamento>(`/mapeamento/estacionamentos/${estacionamento_id}`, { tipo: 'fechado', ...posicao }),
  informarPreco: (estacionamento_id: string, preco_hora: number, posicao: Coordenada) =>
    post<ResultadoMapeamento>(`/mapeamento/estacionamentos/${estacionamento_id}`, {
      tipo: 'preco',
      preco_hora,
      ...posicao,
    }),
  sugerirEstacionamento: (nome: string, preco_hora: number | null, posicao: Coordenada) =>
    post<ResultadoSugestao>('/mapeamento/sugestoes', { nome, preco_hora, ...posicao }),
};
