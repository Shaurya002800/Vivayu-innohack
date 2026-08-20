import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "VIVAYU Aqua",
  description: "Scarcity-aware, water-quality-aware irrigation",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
