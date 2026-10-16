import { Stack, router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { Botao } from '@/componentes/Botao';
import { api } from '@/lib/api';
import { duracaoMs, useApp } from '@/lib/estado';
import { abrirNavegacao, agendarAvisoDeExpiracao } from '@/lib/externos';
import { cores, corPorProbabilidade, hora, reais } from '@/lib/formato';

const NOMES_COMPONENTES: Record<string, string> = {
  prob_livre: 'Chance de vaga',
  preco: 'Preço',
  caminhada: 'Caminhada',
  tempo_carro: 'Tempo de carro',
  confianca: 'Confiança do dado',
};

export default function TelaVaga() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { recomendacao, vagas, origem, reserva, setReserva, sessaoLocal, setSessaoLocal } = useApp();
  const [placa, setPlaca] = useState('ABC1D23');
  const [ocupado, setOcupado] = useState<string | null>(null);

  const candidato = recomendacao?.candidatos.find((c) => c.id === id);
  const vaga = candidato ?? vagas.find((v) => v.id === id);
  if (!vaga) {
    return (
      <View style={estilos.vazio}>
        <Text style={estilos.texto}>Vaga não encontrada.</Text>
      </View>
    );
  }

  const ehRua = vaga.tipo === 'rua';
  const reservaDestaVaga = reserva?.estacionamento_id === vaga.id && reserva.status === 'ativa' ? reserva : null;
  const duracao = recomendacao?.duracao_min ?? 60;

  async function executar(chave: string, acao: () => Promise<void>) {
    setOcupado(chave);
    try {
      await acao();
    } catch (e) {
      Alert.alert('Não deu certo', (e as Error).message);
    } finally {
      setOcupado(null);
    }
  }

  const reservar = () =>
    executar('reserva', async () => {
      setReserva(await api.reservar(vaga.id));
    });

  const cancelarReserva = () =>
    executar('reserva', async () => {
      if (reservaDestaVaga) setReserva(await api.cancelarReserva(reservaDestaVaga.id));
    });

  const iniciarSessao = () =>
    executar('sessao', async () => {
      const sessao = await api.iniciarSessao(vaga.id, placa, duracao);
      const inicioLocal = Date.now();
      const avisoId = await agendarAvisoDeExpiracao(new Date(inicioLocal + duracaoMs(sessao)));
      setSessaoLocal({ sessao, inicioLocal, avisoId });
      router.replace('/sessao');
    });

  const reportar = (livre: boolean) =>
    executar(livre ? 'livre' : 'ocupada', async () => {
      // Antifraude da API: o reporte só vale perto da vaga. Com origem simulada, não mandamos posição.
      const posicao = origem && !origem.simulada ? origem : undefined;
      await api.reportar(vaga.id, livre, posicao?.lat, posicao?.lng);
      Alert.alert('Obrigado!', 'Seu reporte ajuda outros motoristas nos próximos minutos.');
    });

  const avaliarChegada = (encontrou: boolean) =>
    executar(encontrou ? 'sim' : 'nao', async () => {
      await api.avaliarChegada(vaga.id, encontrou);
      Alert.alert('Obrigado!', 'Isso entra na nossa taxa de acerto.');
    });

  return (
    <ScrollView contentContainerStyle={estilos.conteudo}>
      <Stack.Screen options={{ title: ehRua ? 'Vaga de rua' : 'Estacionamento' }} />

      <Text style={estilos.titulo}>{vaga.nome}</Text>
      <View style={[estilos.estado, { borderLeftColor: corPorProbabilidade(vaga.estado.prob_livre) }]}>
        <Text style={estilos.estadoRotulo}>{vaga.estado.rotulo}</Text>
        <Text style={estilos.suave}>
          Chance estimada de vaga: {Math.round(vaga.estado.prob_livre * 100)}% · confiança{' '}
          {Math.round(vaga.estado.confianca * 100)}%
        </Text>
      </View>

      {candidato && (
        <View style={estilos.bloco}>
          <Text style={estilos.texto}>
            {reais(candidato.preco_estimado)} por {duracao < 60 ? `${duracao} min` : `${duracao / 60} h`} ·{' '}
            {candidato.caminhada_min} min a pé ({candidato.caminhada_m} m)
            {candidato.tempo_carro_min !== null ? ` · ${candidato.tempo_carro_min} min de carro` : ''}
          </Text>
          {candidato.motivos.map((m) => (
            <Text key={m} style={estilos.motivo}>✓ {m}</Text>
          ))}
          {candidato.avisos.map((a) => (
            <Text key={a} style={estilos.aviso}>! {a}</Text>
          ))}
          <Text style={[estilos.subtitulo, { marginTop: 8 }]}>Por que esta posição (nota {candidato.nota.toFixed(2)})</Text>
          {Object.entries(candidato.componentes).map(([chave, valor]) => (
            <View key={chave} style={estilos.barraLinha}>
              <Text style={estilos.barraNome}>{NOMES_COMPONENTES[chave] ?? chave}</Text>
              <View style={estilos.barraFundo}>
                <View style={[estilos.barra, { width: `${Math.round(valor * 100)}%` }]} />
              </View>
            </View>
          ))}
        </View>
      )}

      <Text style={estilos.subtitulo}>Ir até a vaga</Text>
      <View style={estilos.linha}>
        <Botao titulo="Waze" onPress={() => abrirNavegacao('waze', vaga.lat, vaga.lng)} />
        <Botao titulo="Google Maps" onPress={() => abrirNavegacao('google', vaga.lat, vaga.lng)} />
      </View>

      {!ehRua && (candidato?.pode_reservar || reservaDestaVaga) && (
        <>
          <Text style={estilos.subtitulo}>Reserva (parceiro)</Text>
          {reservaDestaVaga ? (
            <View style={estilos.bloco}>
              <Text style={estilos.texto}>
                Código <Text style={{ fontWeight: '700' }}>{reservaDestaVaga.codigo}</Text> · válida até{' '}
                {hora(reservaDestaVaga.expira_em)}
              </Text>
              <Text style={estilos.suave}>Mostre o código ou a placa na cancela.</Text>
              <Botao titulo="Cancelar reserva" variante="secundario" carregando={ocupado === 'reserva'} onPress={cancelarReserva} />
            </View>
          ) : (
            <Botao titulo="Reservar por 10 min" carregando={ocupado === 'reserva'} onPress={reservar} />
          )}
        </>
      )}
      {ehRua && <Text style={estilos.suave}>Vagas de rua (EstaR) são espaço público e não podem ser reservadas.</Text>}

      <Text style={estilos.subtitulo}>Estacionar (pagamento simulado)</Text>
      <View style={estilos.bloco}>
        <Text style={estilos.suave}>
          {ehRua
            ? 'No MVP nada é cobrado. Na versão real, o EstaR é pago por um app homologado pela URBS.'
            : 'No MVP nada é cobrado. Na versão real, o pagamento será por Pix ou cartão.'}
        </Text>
        <TextInput
          value={placa}
          onChangeText={(t) => setPlaca(t.toUpperCase())}
          autoCapitalize="characters"
          placeholder="Placa"
          style={estilos.campo}
        />
        <Botao
          titulo={sessaoLocal ? 'Você já tem um estacionamento ativo' : 'Iniciar estacionamento'}
          desabilitado={!!sessaoLocal}
          carregando={ocupado === 'sessao'}
          onPress={iniciarSessao}
        />
      </View>

      {ehRua && (
        <>
          <Text style={estilos.subtitulo}>Está vendo esta vaga agora?</Text>
          <View style={estilos.linha}>
            <Botao titulo="Está livre" variante="secundario" carregando={ocupado === 'livre'} onPress={() => reportar(true)} />
            <Botao titulo="Está ocupada" variante="secundario" carregando={ocupado === 'ocupada'} onPress={() => reportar(false)} />
          </View>
        </>
      )}

      <Text style={estilos.subtitulo}>Chegou? Encontrou a vaga?</Text>
      <View style={estilos.linha}>
        <Botao titulo="Sim" variante="secundario" carregando={ocupado === 'sim'} onPress={() => avaliarChegada(true)} />
        <Botao titulo="Não" variante="secundario" carregando={ocupado === 'nao'} onPress={() => avaliarChegada(false)} />
      </View>
    </ScrollView>
  );
}

const estilos = StyleSheet.create({
  conteudo: { padding: 16, gap: 12, paddingBottom: 40, backgroundColor: cores.fundo },
  vazio: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  titulo: { fontSize: 22, fontWeight: '700', color: cores.marinho },
  subtitulo: { fontSize: 15, fontWeight: '700', color: cores.texto, marginTop: 4 },
  texto: { fontSize: 15, color: cores.texto },
  suave: { fontSize: 13, color: cores.suave },
  estado: { backgroundColor: '#fff', borderRadius: 10, padding: 12, borderLeftWidth: 6, gap: 4 },
  estadoRotulo: { fontSize: 16, fontWeight: '600', color: cores.texto },
  bloco: { backgroundColor: '#fff', borderRadius: 10, padding: 12, gap: 6 },
  motivo: { fontSize: 14, color: cores.livre },
  aviso: { fontSize: 14, color: cores.talvez },
  linha: { flexDirection: 'row', gap: 10 },
  campo: { borderWidth: 1, borderColor: cores.borda, borderRadius: 10, paddingHorizontal: 12, minHeight: 46, fontSize: 16, color: cores.texto },
  barraLinha: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  barraNome: { width: 120, fontSize: 13, color: cores.suave },
  barraFundo: { flex: 1, height: 8, borderRadius: 4, backgroundColor: cores.borda, overflow: 'hidden' },
  barra: { height: 8, backgroundColor: cores.azul },
});
