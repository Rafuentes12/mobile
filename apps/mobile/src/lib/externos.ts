import * as Linking from 'expo-linking';
import * as Location from 'expo-location';
import * as Notifications from 'expo-notifications';

import { distanciaKm } from './formato';

// Navegação curva a curva fica com o Waze/Google Maps (planejamento, seção 8):
// sem custo de API e o motorista já conhece esses apps.
export function abrirNavegacao(app: 'waze' | 'google', lat: number, lng: number) {
  const url =
    app === 'waze'
      ? `https://waze.com/ul?ll=${lat},${lng}&navigate=yes`
      : `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}&travelmode=driving`;
  return Linking.openURL(url);
}

// Se a pessoa não está em Curitiba (ou negou a localização), simulamos uma origem
// na Rodoferroviária para que o tempo de carro faça sentido nos testes.
const CENTRO_CURITIBA = { lat: -25.4296, lng: -49.2713 };
const ORIGEM_SIMULADA = { lat: -25.437, lng: -49.2565 };

export async function obterOrigem(): Promise<{ lat: number; lng: number; simulada: boolean }> {
  try {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status === 'granted') {
      const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
      const atual = { lat: pos.coords.latitude, lng: pos.coords.longitude };
      if (distanciaKm(atual, CENTRO_CURITIBA) < 30) return { ...atual, simulada: false };
    }
  } catch {
    // segue com a origem simulada
  }
  return { ...ORIGEM_SIMULADA, simulada: true };
}

// Aviso de expiração agendado no próprio celular: funciona sem servidor (seção 7, passo 9).
const ANTECEDENCIA_MS = 10 * 60 * 1000;

export async function agendarAvisoDeExpiracao(fim: Date): Promise<string | null> {
  const { granted } = await Notifications.requestPermissionsAsync();
  if (!granted) return null;
  const quando = new Date(Math.max(fim.getTime() - ANTECEDENCIA_MS, Date.now() + 5_000));
  return Notifications.scheduleNotificationAsync({
    content: {
      title: 'Seu estacionamento está acabando',
      body: 'Faltam poucos minutos. Abra o VagaCerta para estender com um toque.',
      data: { rota: '/sessao' },
    },
    trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: quando },
  });
}

export async function cancelarAviso(id: string | null) {
  if (id) await Notifications.cancelScheduledNotificationAsync(id);
}
