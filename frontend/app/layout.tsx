import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "SCM 원자재 리스크 대시보드",
  description: "Next.js + FastAPI 대시보드",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
