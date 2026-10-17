import { router } from 'expo-router';
import { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { Botao } from '@/componentes/Botao';
import { api } from '@/lib/api';
import { useApp } from '@/lib/estado';
import { posicaoAtual } from '@/lib/externos';
import { cores } from '@/lib/formato';
import { RAIO_VAGAS_M, REGIAO_PILOTO } from '@/lib/regiao';

// Estacionamento que falta no mapa. A sugestão usa a posição atual: é feita na porta do local.
export default function TelaSugerir() {
  const { setVagas } = useApp();
  const [nome, setNome] = useState('');
  const [preco, setPreco] = useState('');
  const [enviando, setEnviando] = useState(false);

  async function enviar() {
    setEnviando(true);
    try {
      const valor = preco ? Number(preco.replace(',', '.')) : null;
      if (valor !== null && Number.isNaN(valor)) throw new Error('Digite o preço por hora, por exemplo 12,50.');
      const r = await api.sugerirEstacionamento(nome, valor, await posicaoAtual());
      if (r.status === 'confirmada') {
        await api.vagas(REGIAO_PILOTO.latitude, REGIAO_PILOTO.longitude, RAIO_VAGAS_M).then(setVagas);
      }
      Alert.alert('Obrigado!', r.mensagem, [{ text: 'OK', onPress: () => router.back() }]);
    } catch (e) {
      Alert.alert('Não deu certo', (e as Error).message);
    } finally {
      setEnviando(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={estilos.conteudo}>
      <Text style={estilos.texto}>
        Está na frente de um estacionamento que não aparece no mapa? Envie daqui mesmo: usamos a sua localização
        atual como endereço.
      </Text>
      <Text style={estilos.suave}>
        Ele aparece para todos quando outro motorista confirmar (2 sugestões no mesmo lugar).
      </Text>
      <View style={estilos.bloco}>
        <Text style={estilos.rotulo}>Nome</Text>
        <TextInput value={nome} onChangeText={setNome} placeholder="Ex.: Estacionamento Central" style={estilos.campo} />
        <Text style={estilos.rotulo}>Preço por hora (opcional)</Text>
        <TextInput
          value={preco}
          onChangeText={setPreco}
          keyboardType="decimal-pad"
          placeholder="Ex.: 12,50"
          style={estilos.campo}
        />
      </View>
      <View style={estilos.linha}>
        <Botao titulo="Enviar sugestão" desabilitado={nome.trim().length < 3} carregando={enviando} onPress={enviar} />
      </View>
    </ScrollView>
  );
}

const estilos = StyleSheet.create({
  conteudo: { padding: 16, gap: 12, backgroundColor: cores.fundo, flexGrow: 1 },
  texto: { fontSize: 15, color: cores.texto },
  suave: { fontSize: 13, color: cores.suave },
  bloco: { backgroundColor: '#fff', borderRadius: 10, padding: 12, gap: 8 },
  rotulo: { fontSize: 14, fontWeight: '600', color: cores.texto },
  campo: { borderWidth: 1, borderColor: cores.borda, borderRadius: 10, paddingHorizontal: 12, minHeight: 46, fontSize: 16, color: cores.texto },
  linha: { flexDirection: 'row' },
});
