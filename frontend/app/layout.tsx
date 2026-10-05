import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";

const spaceGrotesk = localFont({
  src: "./fonts/SpaceGrotesk-latin.woff2",
  weight: "300 700",
  style: "normal",
  display: "swap",
  variable: "--font-space-grotesk",
});

const aldrich = localFont({
  src: "./fonts/Aldrich-latin.woff2",
  weight: "400",
  style: "normal",
  display: "swap",
  variable: "--font-aldrich",
});

export const metadata: Metadata = {
  title: "SAULI",
  description: "SAULI account portal",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`h-full antialiased ${spaceGrotesk.variable} ${aldrich.variable}`}
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
