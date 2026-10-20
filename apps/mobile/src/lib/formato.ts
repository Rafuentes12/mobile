export const cores = {
  marinho: '#21285A',
  azul: '#0B5A80',
  fundo: '#F3F6F9',
  texto: '#1D2433',
  suave: '#5B6578',
  borda: '#DCE3EA',
  livre: '#1E8E4F',
  talvez: '#C98500',
  ocupada: '#C62828',
  proibida: '#8A94A6',
  // Versões claras: estimativa do modelo, sem dado ao vivo.
  livreSuave: '#8CCBA5',
  talvezSuave: '#E8C77A',
  ocupadaSuave: '#E59A9A',
};

// Cores fortes só com dado ao vivo; sem ele, as versões claras (é só estimativa).
export function corDoEstado(estado: { nivel: 'facil' | 'moderado' | 'dificil'; ao_vivo: boolean }): string {
  const forte = { facil: cores.livre, moderado: cores.talvez, dificil: cores.ocupada };
  const suave = { facil: cores.livreSuave, moderado: cores.talvezSuave, dificil: cores.ocupadaSuave };
  return (estado.ao_vivo ? forte : suave)[estado.nivel];
}

export function reais(valor: number | null): string {
  if (valor === null) return 'Preço não informado';
  return valor === 0 ? 'Grátis' : `R$ ${valor.toFixed(2).replace('.', ',')}`;
}

export function metros(valor: number): string {
  return valor >= 1000 ? `${(valor / 1000).toFixed(1).replace('.', ',')} km` : `${Math.round(valor)} m`;
}

export function hora(iso: string | Date): string {
  return new Date(iso).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}

export function distanciaKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const rad = (g: number) => (g * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

// Menor distância (m) de um ponto até uma linha — mesma conta que a API usa para a regra dos 300 m.
export function distanciaAteLinha(p: { lat: number; lng: number }, linha: [number, number][]): number {
  if (linha.length === 1) return distanciaKm(p, { lat: linha[0][0], lng: linha[0][1] }) * 1000;
  const escala = Math.cos((p.lat * Math.PI) / 180) * 111_320;
  const plano = (lat: number, lng: number) => [lng * escala, lat * 111_320];
  const [px, py] = plano(p.lat, p.lng);
  let menor = Infinity;
  for (let i = 0; i < linha.length - 1; i++) {
    const [ax, ay] = plano(linha[i][0], linha[i][1]);
    const [bx, by] = plano(linha[i + 1][0], linha[i + 1][1]);
    const dx = bx - ax;
    const dy = by - ay;
    const comp2 = dx * dx + dy * dy;
    const t = comp2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / comp2));
    menor = Math.min(menor, Math.hypot(px - (ax + t * dx), py - (ay + t * dy)));
  }
  return menor;
}
