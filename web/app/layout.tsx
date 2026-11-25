import type { Metadata, Viewport } from "next";
import { Archivo, Figtree, Martian_Mono } from "next/font/google";
import "./globals.css";

const mono = Martian_Mono({ variable: "--f-mono", subsets: ["latin"], axes: ["wdth"] });
// app da maquininha no estilo do site da Stone: ABC Gravity (títulos condensados) e Roobert (texto) são fontes pagas;
// Archivo em largura 62 e Figtree são as equivalentes livres mais próximas
const titulo = Archivo({ variable: "--f-titulo", subsets: ["latin"], axes: ["wdth"] });
const texto = Figtree({ variable: "--f-texto", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Conversa · Case Stone",
  description: "Digite um post na maquininha e receba o extrato de conversa: o que ajuda, o que atrapalha e a nota de aderência.",
  openGraph: {
    title: "Conversa · Case Stone",
    description: "Digite um post na maquininha e receba o extrato de conversa: o que ajuda, o que atrapalha e a nota de aderência.",
    type: "website", locale: "pt_BR",
  },
};

export const viewport: Viewport = { themeColor: "#020805" };

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="pt-BR" className={`${mono.variable} ${titulo.variable} ${texto.variable}`}>
      <body>{children}</body>
    </html>
  );
}
