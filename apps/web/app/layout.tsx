import type { Metadata } from "next";
import { Schibsted_Grotesk } from "next/font/google";
import type { ReactNode } from "react";

import { Shell } from "@/components/shell";

import "./globals.css";

const sans = Schibsted_Grotesk({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Clip Studio",
  description: "Plataforma self-hosted para clipar vídeos longos.",
};

type RootLayoutProps = {
  children: ReactNode;
};

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="pt-BR">
      <body className={`${sans.className} antialiased`}>
        <Shell>{children}</Shell>
      </body>
    </html>
  );
}
