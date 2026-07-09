import React from 'react';
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChatBoxSettings } from '@/types/data';
import { getAuthEmail, clearAuth } from '@/helpers/auth';

interface FooterProps {
  chatBoxSettings: ChatBoxSettings;
  setChatBoxSettings: React.Dispatch<React.SetStateAction<ChatBoxSettings>>;
}

const Footer: React.FC<FooterProps> = ({ chatBoxSettings, setChatBoxSettings }) => {
  const router = useRouter();
  const email = typeof window !== 'undefined' ? getAuthEmail() : null;

  const handleLogout = () => {
    clearAuth();
    router.push('/login');
  };

  // Add domain filtering from URL parameters
  if (typeof window !== 'undefined') {
    const urlParams = new URLSearchParams(window.location.search);
    const urlDomains = urlParams.get("domains");
    if (urlDomains) {
      // Split domains by comma if multiple domains are provided
      const domainArray = urlDomains.split(',').map(domain => ({
        value: domain.trim()
      }));
      localStorage.setItem('domainFilters', JSON.stringify(domainArray));
    }
  }

  return (
    <>
      <div className="container flex flex-col sm:flex-row min-h-[60px] sm:min-h-[72px] mt-2 items-center justify-center sm:justify-between border-t border-gray-200/30 px-4 pb-3 pt-4 sm:py-5 lg:px-0 bg-transparent backdrop-blur-sm gap-3 sm:gap-0">
        <div className="text-xs sm:text-sm text-gray-800 text-center sm:text-left">
            © {new Date().getFullYear()} Bunny Research. All rights reserved.
        </div>
        <div className="flex items-center gap-4 mb-2 sm:mb-0">
          {email && (
            <span className="text-xs text-gray-500 hidden sm:inline">{email}</span>
          )}
          <button
            onClick={handleLogout}
            className="text-xs sm:text-sm text-gray-500 hover:text-gray-700 transition-colors"
          >
            退出登录
          </button>
          <Link href={"https://github.com/blurryface13"} target="_blank" className="p-1">
            <img
              src={"/img/github.svg"}
              alt="github"
              width={24}
              height={24}
              className="w-6 h-6 sm:w-7 sm:h-7"
            />{" "}
          </Link>
        </div>
      </div>
    </>
  );
};

export default Footer;
