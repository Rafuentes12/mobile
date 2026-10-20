import { ActivityIndicator, Pressable, StyleSheet, Text } from 'react-native';

import { cores } from '@/lib/formato';

interface Props {
  titulo: string;
  onPress: () => void;
  variante?: 'principal' | 'secundario' | 'perigo';
  carregando?: boolean;
  desabilitado?: boolean;
  compacto?: boolean; // fonte menor, para vários botões numa linha só
}

export function Botao({ titulo, onPress, variante = 'principal', carregando, desabilitado, compacto }: Props) {
  const inativo = desabilitado || carregando;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      disabled={inativo}
      style={({ pressed }) => [
        estilos.base,
        estilos[variante],
        compacto && estilos.compacto,
        (pressed || inativo) && { opacity: 0.6 },
      ]}
    >
      {carregando ? (
        <ActivityIndicator color={variante === 'secundario' ? cores.azul : '#fff'} />
      ) : (
        <Text
          numberOfLines={1}
          style={[estilos.texto, compacto && estilos.textoCompacto, variante === 'secundario' && { color: cores.azul }]}
        >
          {titulo}
        </Text>
      )}
    </Pressable>
  );
}

const estilos = StyleSheet.create({
  base: { minHeight: 48, borderRadius: 10, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center', flex: 1 },
  principal: { backgroundColor: cores.azul },
  secundario: { backgroundColor: '#fff', borderWidth: 1, borderColor: cores.azul },
  perigo: { backgroundColor: cores.ocupada },
  texto: { color: '#fff', fontWeight: '600', fontSize: 15 },
  compacto: { paddingHorizontal: 6 },
  textoCompacto: { fontSize: 13 },
});
