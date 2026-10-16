// Espelho dos modelos da API (services/api/app/modelos.py).
// Próximo passo do planejamento: gerar estes tipos do OpenAPI com `openapi-typescript`.

export type Contexto = 'urgencia' | 'trabalho' | 'lazer';
export type Credencial = 'nenhuma' | 'idoso' | 'pcd';
export type TipoVaga = 'comum' | 'idoso' | 'pcd' | 'carga_descarga';

export interface Coordenada {
  lat: number;
  lng: number;
}

export interface Destino extends Coordenada {
  id: string;
  nome: string;
  endereco: string;
}

export interface EstadoVaga {
  prob_livre: number;
  vagas_livres_estimadas: number;
  confianca: number;
  fonte: string;
  atualizado_ha_min: number | null;
  rotulo: string;
}

export interface VagaNoMapa extends Coordenada {
  id: string;
  tipo: 'rua' | 'estacionamento';
  nome: string;
  tipo_vaga: TipoVaga | null;
  coordenadas: [number, number][] | null;
  estado: EstadoVaga;
}

export interface Candidato extends Coordenada {
  id: string;
  tipo: 'rua' | 'estacionamento';
  nome: string;
  caminhada_m: number;
  caminhada_min: number;
  tempo_carro_min: number | null;
  preco_estimado: number;
  estado: EstadoVaga;
  pode_reservar: boolean;
  nota: number;
  componentes: Record<string, number>;
  motivos: string[];
  avisos: string[];
}

export interface RespostaRecomendacao {
  destino: Coordenada;
  contexto: Contexto;
  duracao_min: number;
  chegada_prevista: string;
  candidatos: Candidato[];
  descartados: { id: string; nome: string; motivo: string }[];
  mensagem: string | null;
}

export interface Reserva {
  id: string;
  estacionamento_id: string;
  codigo: string;
  criada_em: string;
  expira_em: string;
  status: 'ativa' | 'expirada' | 'cancelada' | 'utilizada';
}

export interface Sessao {
  id: string;
  tipo: 'rua' | 'estacionamento';
  alvo_id: string;
  placa: string;
  inicio: string;
  fim_previsto: string;
  valor_pago: number;
  pagamento: 'simulado';
  status: 'ativa' | 'encerrada';
}
