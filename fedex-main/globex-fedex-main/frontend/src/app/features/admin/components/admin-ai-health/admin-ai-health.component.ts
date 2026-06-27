import { Component, inject, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { AdminAiService, AiHealthSnapshot } from '../../../../core/services/admin-ai.service';

@Component({
  selector: 'app-admin-ai-health',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './admin-ai-health.component.html',
  styleUrl: './admin-ai-health.component.scss',
})
export class AdminAiHealthComponent implements OnInit {
  private readonly api = inject(AdminAiService);

  loading = signal(true);
  health = signal<AiHealthSnapshot | null>(null);
  error = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.api.getHealth().subscribe({
      next: (h) => {
        this.health.set(h);
        this.loading.set(false);
      },
      error: () => {
        this.error.set('Impossible de charger la santé IA.');
        this.loading.set(false);
      },
    });
  }

  statusLabel(status: string): string {
    if (status === 'green') return 'Gemini actif';
    if (status === 'orange') return 'Ollama actif';
    return 'Fallback actif';
  }

  statusClass(status: string): string {
    return `ai-health__status--${status || 'red'}`;
  }

  providerLabel(p: string): string {
    const map: Record<string, string> = {
      gemini: 'Gemini Flash',
      gemini_pro: 'Gemini Pro',
      ollama: 'Ollama',
      local_fallback: 'Fallback local',
    };
    return map[p] || p;
  }
}
