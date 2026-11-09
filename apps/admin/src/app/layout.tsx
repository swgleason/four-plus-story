import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Four Plus Story | Curator Workbench",
  description: "Secure document ingestion and editorial review workbench.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
