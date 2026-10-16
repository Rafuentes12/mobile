import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VagaCerta Parceiros",
  description: "Painel para estacionamentos parceiros informarem vagas livres.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
