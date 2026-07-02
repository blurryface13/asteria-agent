import type { Metadata } from "next";
import { Lexend } from "next/font/google";
import PlausibleProvider from "next-plausible";
import { GoogleAnalytics } from '@next/third-parties/google'
import { ResearchHistoryProvider } from "@/hooks/ResearchHistoryContext";
import AuthGuard from "@/components/AuthGuard";
import "./globals.css";
import Script from 'next/script';

const inter = Lexend({ subsets: ["latin"] });

let title = "Bunny Research";
let description =
  "LLM based autonomous agent that conducts local and web research on any topic and generates a comprehensive report with citations.";
let url = "https://github.com/blurryface13";
let ogimage = "/favicon.ico?v=bunny1";
let sitename = "Bunny Research";

export const metadata: Metadata = {
  metadataBase: new URL(url),
  title,
  description,
  manifest: '/manifest.json',
  icons: {
    icon: "/img/gptr-black-logo.png?v=bunny1",
    apple: '/img/gptr-black-logo.png?v=bunny1',
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: 'default',
    title: title,
  },
  openGraph: {
    images: [ogimage],
    title,
    description,
    url: url,
    siteName: sitename,
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    images: [ogimage],
    title,
    description,
  },
  viewport: {
    width: 'device-width',
    initialScale: 1,
    maximumScale: 1,
    userScalable: false,
  },
  themeColor: '#FFFFFF',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {

  return (
    <html className="gptr-root" lang="en" suppressHydrationWarning>
      <head>
        <PlausibleProvider domain="localhost:3000" />
        <GoogleAnalytics gaId={process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID!} />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-status-bar-style" content="default" />
        <link rel="apple-touch-icon" href="/img/gptr-black-logo.png?v=bunny1" />
      </head>
      <body
        className={`app-container ${inter.className} flex min-h-screen flex-col justify-between`}
        suppressHydrationWarning
      >
        <ResearchHistoryProvider>
          <AuthGuard>
            {children}
          </AuthGuard>
        </ResearchHistoryProvider>
      </body>
    </html>
  );
}
