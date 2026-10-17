import * as Notifications from 'expo-notifications';
import { Stack, router } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';

import { ProvedorEstado } from '@/lib/estado';
import { cores } from '@/lib/formato';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

export default function Layout() {
  // Tocar no aviso de expiração abre a tela da sessão.
  useEffect(() => {
    const assinatura = Notifications.addNotificationResponseReceivedListener((resposta) => {
      const rota = resposta.notification.request.content.data?.rota;
      if (rota === '/sessao') router.push('/sessao');
    });
    return () => assinatura.remove();
  }, []);

  return (
    <ProvedorEstado>
      <StatusBar style="dark" />
      <Stack
        screenOptions={{
          headerTintColor: cores.marinho,
          headerTitleStyle: { fontWeight: '700' },
          headerBackTitle: 'Voltar',
        }}
      >
        <Stack.Screen name="index" options={{ headerShown: false }} />
        <Stack.Screen name="vaga/[id]" options={{ title: 'Vaga' }} />
        <Stack.Screen name="sessao" options={{ title: 'Estacionamento ativo' }} />
        <Stack.Screen name="sugerir" options={{ title: 'Sugerir estacionamento' }} />
      </Stack>
    </ProvedorEstado>
  );
}
