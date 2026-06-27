import { CommonModule } from '@angular/common';
import { Component, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatSnackBar, MatSnackBarModule } from '@angular/material/snack-bar';

import {
  GptKnowledgeProfile,
  GptKnowledgeService,
  KnowledgeDocumentRow,
} from '../../../../core/services/gpt-knowledge.service';

@Component({
  selector: 'app-admin-gpt-knowledge',
  standalone: true,
  imports: [CommonModule, FormsModule, MatSnackBarModule],
  templateUrl: './admin-gpt-knowledge.component.html',
  styleUrl: './admin-gpt-knowledge.component.scss',
})
export class AdminGptKnowledgeComponent implements OnInit {
  readonly loading = signal(true);
  readonly uploading = signal(false);
  readonly reindexing = signal(false);
  readonly profiles = signal<GptKnowledgeProfile[]>([]);
  readonly documents = signal<KnowledgeDocumentRow[]>([]);

  selectedGpt = 'fedex-admin-ops';
  selectedLang = 'fr';

  constructor(
    private readonly api: GptKnowledgeService,
    private readonly snack: MatSnackBar,
  ) {}

  ngOnInit(): void {
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.api.getOverview().subscribe({
      next: (data) => {
        this.profiles.set(data.gpt_profiles ?? []);
        this.loading.set(false);
        this.loadDocuments();
      },
      error: () => {
        this.loading.set(false);
        this.toast('Impossible de charger la base de connaissances.', 'error');
      },
    });
  }

  loadDocuments(): void {
    this.api.getDocuments(this.selectedGpt).subscribe({
      next: (rows) => this.documents.set(rows),
      error: () => this.documents.set([]),
    });
  }

  onGptChange(): void {
    this.loadDocuments();
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || this.uploading()) return;

    this.uploading.set(true);
    this.api.upload(file, this.selectedGpt, this.selectedLang).subscribe({
      next: (res) => {
        this.uploading.set(false);
        input.value = '';
        this.toast(`Document indexé — ${res.chunk_count} fragment(s).`, 'success');
        this.refresh();
      },
      error: (err) => {
        this.uploading.set(false);
        input.value = '';
        const msg = err?.error?.detail || 'Échec upload.';
        this.toast(msg, 'error');
      },
    });
  }

  reindexEmbeddings(): void {
    if (this.reindexing()) return;
    this.reindexing.set(true);
    this.api.reindex(this.selectedGpt).subscribe({
      next: (res) => {
        this.reindexing.set(false);
        this.toast(`${res.reindexed} chunk(s) réindexé(s).`, 'success');
        this.refresh();
      },
      error: () => {
        this.reindexing.set(false);
        this.toast('Réindexation échouée.', 'error');
      },
    });
  }

  deleteDoc(id: number): void {
    if (!confirm('Supprimer ce document et ses fragments ?')) return;
    this.api.deleteDocument(id).subscribe({
      next: () => {
        this.toast('Document supprimé.', 'success');
        this.refresh();
      },
      error: () => this.toast('Suppression impossible.', 'error'),
    });
  }

  formatBytes(n: number): string {
    if (n < 1024) return `${n} o`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} Ko`;
    return `${(n / (1024 * 1024)).toFixed(1)} Mo`;
  }

  private toast(message: string, type: 'success' | 'error'): void {
    this.snack.open(message, 'OK', {
      duration: 4000,
      panelClass: type === 'error' ? 'snack-error' : 'snack-success',
    });
  }
}
