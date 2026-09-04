/**
 * VideoPlayer.jsx
 * Renders video content via iframe (YouTube embed) or HTML5 video tag.
 */

import { PlayCircle } from 'lucide-react';

export default function VideoPlayer({ url, title }) {
  if (!url) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <PlayCircle size={48} className="mb-2 opacity-30" />
        <p>Video URL belum tersedia</p>
      </div>
    );
  }

  // Detect YouTube / Vimeo iframe-friendly URLs
  const isEmbeddable = /youtube\.com\/embed|vimeo\.com\/video|player\.vimeo/.test(url);
  // Direct mp4/webm/ogv?
  const isDirectVideo = /\.(mp4|webm|ogv|mov)(\?.*)?$/i.test(url);

  if (isEmbeddable) {
    return (
      <div className="relative w-full" style={{ paddingBottom: '56.25%' }} data-testid="video-player-iframe">
        <iframe
          src={url}
          title={title || 'Video'}
          className="absolute inset-0 w-full h-full rounded-lg"
          frameBorder="0"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
          allowFullScreen
        />
      </div>
    );
  }

  if (isDirectVideo) {
    return (
      <video
        controls
        className="w-full rounded-lg max-h-[500px] bg-black"
        data-testid="video-player-html5"
      >
        <source src={url} />
        Browser Anda tidak mendukung HTML5 video.
      </video>
    );
  }

  // Fallback: external link
  return (
    <div className="text-center py-12" data-testid="video-player-link">
      <PlayCircle size={48} className="mx-auto mb-2 text-muted-foreground" />
      <p className="text-sm text-muted-foreground mb-2">URL tidak dapat di-embed</p>
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="text-primary underline"
      >
        Buka video di tab baru
      </a>
    </div>
  );
}
