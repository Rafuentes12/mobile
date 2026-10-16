import { router } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Keyboard,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import MapView, { Marker, Polyline } from 'react-native-maps';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Botao } from '@/componentes/Botao';
import { api } from '@/lib/api';
import { duracaoMs, useApp } from '@/lib/estado';
import { obterOrigem } from '@/lib/externos';
import { cores, corPorProbabilidade, hora, reais } from '@/lib/formato';
import type { Contexto, Credencial, Destino } from '@/lib/tipos';

const REGIAO_PILOTO = { latitude: -25.437, longitude: -49.2795, latitudeDelta: 0.03, longitudeDelta: 0.03 };
const INTERVALO_ATUALIZACAO_MS = 30_000; // polling no MVP; WebSocket no Piloto

const CONTEXTOS: { valor: Contexto; rotulo: string }[] = [
  { valor: 'urgencia', rotulo: 'Urgência' },
  { valor: 'trabalho', rotulo: 'Trabalho' },
  { valor: 'lazer', rotulo: 'Lazer' },
];
const DURACOES = [30, 60, 120, 180, 480];
const CREDENCIAIS: Credencial[] = ['nenhuma', 'idoso', 'pcd'];

interface Filtros {
  destino: Destino | null;
  contexto: Contexto;
  duracao_min: number;
  credencial: Credencial;
}

export default function TelaMapa() {
  const { origem, setOrigem, destino, setDestino, vagas, setVagas, recomendacao, setRecomendacao, sessaoLocal } =
    useApp();
  const [texto, setTexto] = useState('');
  const [sugestoes, setSugestoes] = useState<Destino[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [contexto, setContexto] = useState<Contexto>('lazer');
  const [duracao, setDuracao] = useState(60);
  const [credencial, setCredencial] = useState<Credencial>('nenhuma');
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const mapa = useRef<MapView>(null);

  useEffect(() => {
    obterOrigem().then(setOrigem);
  }, [setOrigem]);

  // Estado das vagas no mapa, atualizado periodicamente.
  useEffect(() => {
    let ativo = true;
    const carregar = () =>
      api
        .vagas(REGIAO_PILOTO.latitude, REGIAO_PILOTO.longitude, 2500)
        .then((v) => ativo && (setVagas(v), setErro(null)))
        .catch((e: Error) => ativo && setErro(e.message));
    carregar();
    const id = setInterval(carregar, INTERVALO_ATUALIZACAO_MS);
    return () => {
      ativo = false;
      clearInterval(id);
    };
  }, [setVagas]);

  // Sugestões de destino (mock hoje; Google Places via API depois).
  useEffect(() => {
    if (!buscando) return;
    const id = setTimeout(() => api.destinos(texto).then(setSugestoes).catch(() => setSugestoes([])), 250);
    return () => clearTimeout(id);
  }, [texto, buscando]);

  // Disparada pelas ações do usuário (destino, contexto, duração, credencial), não por efeito.
  async function recomendar(filtros: Filtros) {
    if (!filtros.destino) return;
    setCarregando(true);
    setErro(null);
    try {
      const r = await api.recomendacoes({ ...filtros, destino: filtros.destino, origem });
      setRecomendacao(r);
      const pontos = [filtros.destino, ...r.candidatos].map((p) => ({ latitude: p.lat, longitude: p.lng }));
      mapa.current?.fitToCoordinates(pontos, {
        edgePadding: { top: 260, right: 40, bottom: 320, left: 40 },
        animated: true,
      });
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setCarregando(false);
    }
  }

  const filtrosAtuais: Filtros = { destino, contexto, duracao_min: duracao, credencial };

  function mudarFiltro(mudanca: Partial<Filtros>) {
    if (mudanca.contexto) setContexto(mudanca.contexto);
    if (mudanca.duracao_min) setDuracao(mudanca.duracao_min);
    if (mudanca.credencial) setCredencial(mudanca.credencial);
    recomendar({ ...filtrosAtuais, ...mudanca });
  }

  function escolherDestino(d: Destino) {
    setDestino(d);
    setTexto(d.nome);
    setBuscando(false);
    setSugestoes([]);
    Keyboard.dismiss();
    recomendar({ ...filtrosAtuais, destino: d });
  }

  return (
    <View style={estilos.tela}>
      <MapView ref={mapa} style={StyleSheet.absoluteFill} initialRegion={REGIAO_PILOTO} showsUserLocation>
        {vagas
          .filter((v) => v.tipo === 'rua' && v.coordenadas)
          .map((v) => (
            <Polyline
              key={v.id}
              coordinates={v.coordenadas!.map(([latitude, longitude]) => ({ latitude, longitude }))}
              strokeColor={corPorProbabilidade(v.estado.prob_livre)}
              strokeWidth={6}
              tappable
              onPress={() => router.push(`/vaga/${v.id}`)}
            />
          ))}
        {vagas
          .filter((v) => v.tipo === 'estacionamento')
          .map((v) => (
            <Marker
              key={v.id}
              coordinate={{ latitude: v.lat, longitude: v.lng }}
              pinColor={corPorProbabilidade(v.estado.prob_livre)}
              title={v.nome}
              description={v.estado.rotulo}
              onCalloutPress={() => router.push(`/vaga/${v.id}`)}
            />
          ))}
        {destino && (
          <Marker
            coordinate={{ latitude: destino.lat, longitude: destino.lng }}
            pinColor={cores.marinho}
            title={`Destino: ${destino.nome}`}
          />
        )}
      </MapView>

      <SafeAreaView edges={['top']} style={estilos.topo}>
        <View style={estilos.cartao}>
          <TextInput
            value={texto}
            onChangeText={(t) => {
              setTexto(t);
              setBuscando(true);
            }}
            onFocus={() => setBuscando(true)}
            placeholder="Para onde você vai?"
            placeholderTextColor={cores.suave}
            style={estilos.busca}
            returnKeyType="search"
          />
          {buscando &&
            sugestoes.map((s) => (
              <Pressable key={s.id} onPress={() => escolherDestino(s)} style={estilos.sugestao}>
                <Text style={estilos.sugestaoNome}>{s.nome}</Text>
                <Text style={estilos.sugestaoEndereco}>{s.endereco}</Text>
              </Pressable>
            ))}
          <Chips opcoes={CONTEXTOS} valor={contexto} onChange={(contexto) => mudarFiltro({ contexto })} />
          <Chips
            opcoes={DURACOES.map((d) => ({ valor: d, rotulo: d < 60 ? `${d} min` : `${d / 60} h` }))}
            valor={duracao}
            onChange={(duracao_min) => mudarFiltro({ duracao_min })}
          />
          <Chips
            opcoes={CREDENCIAIS.map((c) => ({ valor: c, rotulo: c === 'nenhuma' ? 'Sem credencial' : c.toUpperCase() }))}
            valor={credencial}
            onChange={(credencial) => mudarFiltro({ credencial })}
          />
        </View>
      </SafeAreaView>

      <View style={estilos.painel}>
        {sessaoLocal && (
          <Pressable style={estilos.faixaSessao} onPress={() => router.push('/sessao')}>
            <Text style={estilos.faixaSessaoTexto}>
              Estacionamento ativo até {hora(new Date(sessaoLocal.inicioLocal + duracaoMs(sessaoLocal.sessao)))} · ver
            </Text>
          </Pressable>
        )}
        {erro && <Text style={estilos.erro}>{erro}</Text>}
        {origem?.simulada && !destino && (
          <Text style={estilos.nota}>Fora de Curitiba: usando uma origem simulada no centro.</Text>
        )}
        {!destino && <Text style={estilos.nota}>Escolha um destino no Centro ou no Batel para ver as vagas.</Text>}
        {carregando && <ActivityIndicator color={cores.azul} style={{ marginVertical: 12 }} />}
        {recomendacao && !carregando && (
          <ScrollView style={{ maxHeight: 280 }} contentContainerStyle={{ gap: 8 }}>
            {recomendacao.mensagem && <Text style={estilos.nota}>{recomendacao.mensagem}</Text>}
            {recomendacao.candidatos.map((c, i) => (
              <Pressable key={c.id} style={estilos.item} onPress={() => router.push(`/vaga/${c.id}`)}>
                <View style={[estilos.indicador, { backgroundColor: corPorProbabilidade(c.estado.prob_livre) }]} />
                <View style={{ flex: 1 }}>
                  <Text style={estilos.itemNome} numberOfLines={1}>
                    {i + 1}. {c.nome}
                  </Text>
                  <Text style={estilos.itemRotulo}>{c.estado.rotulo}</Text>
                  <Text style={estilos.itemDetalhe}>
                    {reais(c.preco_estimado)} · {c.caminhada_min} min a pé
                    {c.tempo_carro_min !== null ? ` · ${c.tempo_carro_min} min de carro` : ''}
                    {c.pode_reservar ? ' · reserva' : ''}
                  </Text>
                </View>
              </Pressable>
            ))}
            {recomendacao.descartados.length > 0 && (
              <Text style={estilos.nota}>
                {recomendacao.descartados.length} vaga(s) fora: {recomendacao.descartados[0].motivo.toLowerCase()}
                {recomendacao.descartados.length > 1 ? '…' : ''}
              </Text>
            )}
          </ScrollView>
        )}
        {destino && !carregando && <Botao titulo="Atualizar recomendação" variante="secundario" onPress={() => recomendar(filtrosAtuais)} />}
      </View>
    </View>
  );
}

function Chips<T extends string | number>({
  opcoes,
  valor,
  onChange,
}: {
  opcoes: { valor: T; rotulo: string }[];
  valor: T;
  onChange: (v: T) => void;
}) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={estilos.chips}>
      {opcoes.map((o) => {
        const ativo = o.valor === valor;
        return (
          <Pressable
            key={String(o.valor)}
            onPress={() => onChange(o.valor)}
            style={[estilos.chip, ativo && estilos.chipAtivo]}
            accessibilityState={{ selected: ativo }}
          >
            <Text style={[estilos.chipTexto, ativo && { color: '#fff' }]}>{o.rotulo}</Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const estilos = StyleSheet.create({
  tela: { flex: 1, backgroundColor: cores.fundo },
  topo: { position: 'absolute', top: 0, left: 0, right: 0, paddingHorizontal: 12 },
  cartao: { backgroundColor: '#fff', borderRadius: 14, padding: 12, gap: 8, elevation: 4, shadowOpacity: 0.12, shadowRadius: 8, shadowOffset: { width: 0, height: 2 } },
  busca: { fontSize: 16, color: cores.texto, borderWidth: 1, borderColor: cores.borda, borderRadius: 10, paddingHorizontal: 12, minHeight: 46 },
  sugestao: { paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderColor: cores.borda },
  sugestaoNome: { fontSize: 15, fontWeight: '600', color: cores.texto },
  sugestaoEndereco: { fontSize: 13, color: cores.suave },
  chips: { gap: 6 },
  chip: { paddingHorizontal: 12, minHeight: 34, justifyContent: 'center', borderRadius: 17, borderWidth: 1, borderColor: cores.borda, backgroundColor: '#fff' },
  chipAtivo: { backgroundColor: cores.marinho, borderColor: cores.marinho },
  chipTexto: { fontSize: 13, color: cores.texto, fontWeight: '500' },
  painel: { position: 'absolute', left: 0, right: 0, bottom: 0, backgroundColor: '#fff', borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: 14, paddingBottom: 30, gap: 8, elevation: 8, shadowOpacity: 0.15, shadowRadius: 10 },
  faixaSessao: { backgroundColor: cores.marinho, borderRadius: 10, padding: 10 },
  faixaSessaoTexto: { color: '#fff', fontWeight: '600', textAlign: 'center' },
  erro: { color: cores.ocupada, fontSize: 14 },
  nota: { color: cores.suave, fontSize: 14 },
  item: { flexDirection: 'row', gap: 10, padding: 10, borderRadius: 10, backgroundColor: cores.fundo },
  indicador: { width: 6, borderRadius: 3 },
  itemNome: { fontSize: 15, fontWeight: '700', color: cores.texto },
  itemRotulo: { fontSize: 13, color: cores.texto, marginTop: 2 },
  itemDetalhe: { fontSize: 13, color: cores.suave, marginTop: 2 },
});
