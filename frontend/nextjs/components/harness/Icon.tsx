import React from "react";

const paths: Record<string, React.ReactNode> = {
  more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
  compose: <><path d="M12 4H5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h13a2 2 0 0 0 2-2v-7" /><path d="m16 3 5 5-10 10-5 1 1-5Z" /></>,
  panel: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <path d="M9 4v16" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  new: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="3" strokeDasharray="3 3" />
      <path d="m10 8 7 4-4 1-1 4-2-9Z" />
    </>
  ),
  host: (
    <>
      <rect x="4" y="4" width="16" height="12" rx="2" />
      <path d="m4 16-2 4h20l-2-4" />
    </>
  ),
  agent: (
    <>
      <rect x="4" y="7" width="16" height="13" rx="4" />
      <path d="M12 3v4M8 12v2m8-2v2m-8 3h8M1 11v5m22-5v5" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="7" />
      <path d="m16 16 5 5" />
    </>
  ),
  folder: (
    <path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
  ),
  file: (
    <>
      <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9Z" />
      <path d="M14 3v6h6M8 13h8m-8 4h6" />
    </>
  ),
  cloud: (
    <>
      <path d="M7 17H6a4 4 0 0 1-1-8 7 7 0 0 1 13-2 5 5 0 0 1 0 10h-1M12 12v9m-3-3 3 3 3-3" />
    </>
  ),
  team: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3 20v-3a6 6 0 0 1 12 0v3M16 5a3 3 0 0 1 0 6m2 3a5 5 0 0 1 3 6" />
    </>
  ),
  skill: (
    <>
      <path d="m4 20 12-12 4 4L8 24M6 2v6M3 5h6m9 11v6m-3-3h6" />
    </>
  ),
  memory: (
    <>
      <path d="M9 4a4 4 0 0 0-6 5 4 4 0 0 0 1 7 4 4 0 0 0 7 4V4a3 3 0 0 0-2 0Zm6 0a4 4 0 0 1 6 5 4 4 0 0 1-1 7 4 4 0 0 1-7 4V4a3 3 0 0 1 2 0Z" />
    </>
  ),
  arrow: <path d="M12 20V4m-6 6 6-6 6 6" />,
  chevron: <path d="m9 5 7 7-7 7" />,
  down: <path d="m7 10 5 5 5-5" />,
  close: <path d="m6 6 12 12M6 18 18 6" />,
  mic: (
    <>
      <rect x="9" y="2" width="6" height="13" rx="3" />
      <path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3m-4 0h8" />
    </>
  ),
  terminal: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <path d="m7 9 3 3-3 3m6 0h4" />
    </>
  ),
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="2" />
      <rect x="14" y="3" width="7" height="7" rx="2" />
      <rect x="3" y="14" width="7" height="7" rx="2" />
      <rect x="14" y="14" width="7" height="7" rx="2" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 8A8 8 0 1 0 21 14M20 3v5h-5" />
    </>
  ),
  download: (
    <>
      <path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" />
    </>
  ),
  check: <path d="m5 12 4 4L19 6" />,
  dots: (
    <>
      <circle cx="5" cy="12" r="1" />
      <circle cx="12" cy="12" r="1" />
      <circle cx="19" cy="12" r="1" />
    </>
  ),
};
export default function Icon({
  name,
  size = 20,
}: {
  name: string;
  size?: number;
}) {
  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name] || paths.file}
    </svg>
  );
}
