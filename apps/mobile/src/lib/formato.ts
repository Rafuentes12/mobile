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
};

export function corPorProbabilidade(p: number): string {
  if (p >= 0.7) return cores.livre;
  if (p >= 0.4) return cores.talvez;
  return cores.ocupada;
}

export function reais(valor: number): string {
  return valor === 0 ? 'Grátis' : `R$ ${valor.toFixed(2).replace('.', ',')}`;
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
