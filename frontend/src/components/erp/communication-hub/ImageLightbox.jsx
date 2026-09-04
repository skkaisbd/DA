/**
 * ImageLightbox — fullscreen image preview overlay with Download button.
 */
import { Download, X } from 'lucide-react';

export default function ImageLightbox({ image, onClose }) {
  if (!image) return null;
  return (
    <div
      className="fixed inset-0 z-[9999] bg-foreground/70 flex items-center justify-center p-4"
      onClick={onClose}
      data-testid="image-lightbox"
    >
      <div className="relative max-w-[90vw] max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
        <img
          src={image.url}
          alt={image.name}
          className="max-w-full max-h-[85vh] object-contain rounded-lg shadow-2xl"
        />
        <div className="absolute top-2 right-2 flex gap-2">
          <a
            href={image.url}
            download={image.name}
            target="_blank"
            rel="noreferrer"
            className="bg-foreground/40 hover:bg-foreground/60 text-foreground rounded-full p-1.5 transition-colors"
            onClick={(e) => e.stopPropagation()}
            title="Download"
          >
            <Download size={16} />
          </a>
          <button
            className="bg-foreground/40 hover:bg-foreground/60 text-foreground rounded-full p-1.5 transition-colors"
            onClick={onClose}
            title="Tutup"
          >
            <X size={16} />
          </button>
        </div>
        {image.name && (
          <p className="absolute bottom-2 left-0 right-0 text-center text-foreground/70 text-xs px-4 truncate">
            {image.name}
          </p>
        )}
      </div>
    </div>
  );
}
