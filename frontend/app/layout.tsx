import type { Metadata } from 'next';
import { AuthProvider } from '@/lib/auth-context';
import { AdminAuthProvider } from '@/lib/admin-auth-context';
import './globals.css';

export const metadata: Metadata = {
  title: 'GRMT — Gudsky Research Management Tool',
  description:
    'AI-assisted conference and paper review platform, developed and maintained ' +
    'by GRMT Pvt. Ltd. with research and development by Gudsky Research Foundation, ' +
    'a Section 8 non-profit, AICTE-approved and DPIIT Startup India recognized.',
  icons: {
    icon: '/images/logo.jpg',
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <AdminAuthProvider>{children}</AdminAuthProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
