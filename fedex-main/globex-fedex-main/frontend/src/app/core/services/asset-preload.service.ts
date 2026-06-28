import { Injectable } from '@angular/core';

/** Précharge les assets visuels lourds pour éviter le pop-in au rendu. */
@Injectable({ providedIn: 'root' })
export class AssetPreloadService {
  private readonly loaded = new Set<string>();

  preload(urls: readonly string[]): void {
    for (const url of urls) {
      if (this.loaded.has(url)) continue;
      this.loaded.add(url);
      const img = new Image();
      img.decoding = 'async';
      (img as HTMLImageElement & { fetchPriority?: string }).fetchPriority = 'high';
      img.src = url;
    }
  }

  preloadAdminVisuals(): void {
    this.preload([
      'assets/admin/hero-bg.png?v=2',
      'assets/admin/ai-brain.webp?v=1',
      'assets/admin/ai-brain.png?v=6',
      'assets/admin/tracking-hero-plane.webp?v=1',
      'assets/admin/tracking-hero-plane.png?v=4',
    ]);
  }
}
