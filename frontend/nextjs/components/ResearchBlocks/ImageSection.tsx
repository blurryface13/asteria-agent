import Image from "next/image"; 
import React, { memo } from 'react';
import ImagesAlbum from '../Images/ImagesAlbum';

interface ImageSectionProps {
  metadata: any;
}

const ImageSection = ({ metadata }: ImageSectionProps) => {
  return (
    <div className="container h-auto w-full shrink-0 rounded-xl border border-white/[0.08] bg-white/[0.04] p-5 shadow-[0_12px_36px_rgba(2,6,23,0.12)] backdrop-blur-md">
      <div className="flex items-start gap-4 pb-3 lg:pb-3.5">
        <img src="/img/image.svg" alt="images" width={24} height={24} />
        <h3 className="text-base font-bold uppercase leading-[152.5%] text-white/75">
          Related Images
        </h3>
      </div>
      <div className="overflow-y-auto max-h-[500px] scrollbar-thin scrollbar-thumb-gray-600 scrollbar-track-gray-300/10">
        <ImagesAlbum images={metadata} />
      </div>
    </div>
  );
};

// Simple memo implementation that compares arrays properly
export default memo(ImageSection, (prevProps, nextProps) => {
  // If both are null/undefined or the same reference, they're equal
  if (prevProps.metadata === nextProps.metadata) return true;
  
  // If one is null/undefined but not the other, they're not equal
  if (!prevProps.metadata || !nextProps.metadata) return false;
  
  // Compare lengths
  if (prevProps.metadata.length !== nextProps.metadata.length) return false;
  
  // Compare each item
  for (let i = 0; i < prevProps.metadata.length; i++) {
    if (prevProps.metadata[i] !== nextProps.metadata[i]) return false;
  }
  
  return true;
});
