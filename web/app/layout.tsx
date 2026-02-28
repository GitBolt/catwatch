import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "CatWatch",
  description: "Drone-based equipment inspection platform",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
