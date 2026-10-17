import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';

import { Botao } from '@/componentes/Botao';
import { api } from '@/lib/api';
import { duracaoMs, useApp } from '@/lib/estado';
import { agendarAvisoDeExpiracao, cancelarAviso } from '@/lib/externos';
import { cores, hora, reais } from '@/lib/formato';

export default function TelaSessao() {
  const { sessaoLocal, setSessaoLocal, vagas } = useApp();
  const [agora, setAgora] = useState(() => Date.now());
  const [ocupado, setOcupado] = useState<'estender' | 'encerrar' | null>(null);

  useEffect(() => {
    const id = setInterval(() => setAgora(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  if (!sessaoLocal) {
    return (
      <View style={estilos.vazio}>
        <Text style={estilos.suave}>Nenhum estacionamento ativo.</Text>
      </View>
    );
  }

  const { sessao, inicioLocal, avisoId } = sessaoLocal;
  const fim = inicioLocal + duracaoMs(sessao);
  const restanteS = Math.max(0, Math.round((fim - agora) / 1000));
  const nome = vagas.find((v) => v.id === sessao.alvo_id)?.nome ?? sessao.alvo_id;

  async function estender() {
    setOcupado('estender');
    try {
      const atualizada = await api.estenderSessao(sessao.id, 30);
      await cancelarAviso(avisoId);
      const novoAviso = await agendarAvisoDeExpiracao(new Date(inicioLocal + duracaoMs(atualizada)));
      setSessaoLocal({ sessao: atualizada, inicioLocal, avisoId: novoAviso });
    } catch (e) {
      Alert.alert('Não foi possível estender', (e as Error).message);
    } finally {
      setOcupado(null);
    }
  }

  async function encerrar() {
    setOcupado('encerrar');
    try {
      await api.encerrarSessao(sessao.id);
      await cancelarAviso(avisoId);
      setSessaoLocal(null);
      router.replace('/');
    } catch (e) {
      Alert.alert('Não foi possível encerrar', (e as Error).message);
      setOcupado(null);
    }
  }

  const minutos = Math.floor(restanteS / 60);
  const segundos = String(restanteS % 60).padStart(2, '0');

  return (
    <View style={estilos.tela}>
      <Text style={estilos.nome}>{nome}</Text>
      <Text style={estilos.suave}>
        Placa {sessao.placa} · {sessao.tipo === 'rua' ? 'EstaR' : 'estacionamento'}
      </Text>

      <View style={estilos.relogio}>
        <Text style={estilos.contador}>
          {minutos}:{segundos}
        </Text>
        <Text style={estilos.suave}>restantes · termina às {hora(new Date(fim))}</Text>
      </View>

      <Text style={estilos.texto}>
        Valor: {sessao.valor_pago === null ? 'pago direto no estacionamento' : reais(sessao.valor_pago)}{' '}
        <Text style={estilos.suave}>(pagamento simulado)</Text>
      </Text>
      <Text style={estilos.suave}>Você recebe um aviso 10 minutos antes de acabar.</Text>

      <View style={estilos.linha}>
        <Botao titulo="Estender 30 min" carregando={ocupado === 'estender'} onPress={estender} />
      </View>
      <View style={estilos.linha}>
        <Botao titulo="Encerrar e liberar a vaga" variante="perigo" carregando={ocupado === 'encerrar'} onPress={encerrar} />
      </View>
      {sessao.tipo === 'rua' && (
        <Text style={estilos.suave}>Ao encerrar, avisamos outros motoristas que esta vaga ficou livre.</Text>
      )}
    </View>
  );
}

const estilos = StyleSheet.create({
  tela: { flex: 1, padding: 16, gap: 12, backgroundColor: cores.fundo },
  vazio: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  nome: { fontSize: 20, fontWeight: '700', color: cores.marinho },
  texto: { fontSize: 15, color: cores.texto },
  suave: { fontSize: 13, color: cores.suave },
  relogio: { backgroundColor: '#fff', borderRadius: 14, padding: 24, alignItems: 'center', gap: 4 },
  contador: { fontSize: 48, fontWeight: '700', color: cores.marinho, fontVariant: ['tabular-nums'] },
  linha: { flexDirection: 'row' },
});
