import type { Metadata } from 'next';
import { Geist, Geist_Mono } from 'next/font/google';
import './globals.css';

const geistSans = Geist({
  variable: '--font-geist-sans',
  subsets: ['latin'],
});

const geistMono = Geist_Mono({
  variable: '--font-geist-mono',
  subsets: ['latin'],
});

export const metadata: Metadata = {
  metadataBase: new URL(
    'https://shopbot-miniapp-salvo.salvo-93.chatgpt.site',
  ),
  title: 'ShopBot Mini App',
  description: 'Demo e-commerce per Telegram con prodotti digitali e fisici.',
  openGraph: {
    title: 'ShopBot Mini App',
    description:
      'Un e-commerce moderno dentro Telegram per prodotti digitali e fisici.',
    images: [{ url: '/og.png', width: 1536, height: 1024 }],
  },
  twitter: {
    card: 'summary_large_image',
    title: 'ShopBot Mini App',
    description:
      'Un e-commerce moderno dentro Telegram per prodotti digitali e fisici.',
    images: ['/og.png'],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="it" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        {children}
      </body>
    </html>
  );
}
