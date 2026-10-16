import { PainelParceiro } from "@/componentes/PainelParceiro";

export default function Inicio() {
  return (
    <main className="pagina">
      <header className="topo">
        <h1>VagaCerta · Painel do parceiro</h1>
        <p>
          Informe quantas vagas estão livres no seu estacionamento. O app dos motoristas mostra essa informação
          com a hora da última atualização.
        </p>
        <p className="aviso-mock">MVP acadêmico: dados mockados, nada é cobrado.</p>
      </header>
      <PainelParceiro />
    </main>
  );
}
