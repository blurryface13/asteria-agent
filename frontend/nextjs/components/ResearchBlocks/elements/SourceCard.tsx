import Image from "next/image";
import { useState, useMemo } from "react";

const SourceCard = ({ source }: { source: { name: string; url: string } }) => {
  const [imageSrc, setImageSrc] = useState(`https://www.google.com/s2/favicons?domain=${source.url}&sz=128`);

  const handleImageError = () => {
    setImageSrc("/img/globe.svg");
  };
  
  // Extract and format the domain from the URL
  const formattedUrl = useMemo(() => {
    try {
      const urlObj = new URL(source.url);
      return urlObj.hostname.replace(/^www\./, '');
    } catch (e) {
      // If URL parsing fails, use the original URL but trim it
      return source.url.length > 50 ? source.url.substring(0, 50) + '...' : source.url;
    }
  }, [source.url]);

  return (
    <div className="flex h-[79px] w-full items-center gap-3 rounded-lg border border-white/[0.08] bg-white/[0.04] px-3 py-2 shadow-sm backdrop-blur-sm transition-colors duration-200 hover:border-teal-300/30 md:w-auto">
      
        <img
          src={imageSrc}
          alt={source.url}
          className="p-1"
          width={44}
          height={44}
          onError={handleImageError}  // Update src on error
        />
      
      <div className="flex max-w-[192px] flex-col justify-center gap-[7px]">
        <h6 className="line-clamp-2 text-sm font-medium leading-[normal] text-white/75">
          {source.name}
        </h6>
        <a
          target="_blank"
          rel="noopener noreferrer"
          href={source.url}
          className="truncate text-sm font-light text-white/35 transition-colors hover:text-teal-200/80"
          title={source.url}
        >
          {formattedUrl}
        </a>
      </div>
    </div>
  );
};

export default SourceCard;
