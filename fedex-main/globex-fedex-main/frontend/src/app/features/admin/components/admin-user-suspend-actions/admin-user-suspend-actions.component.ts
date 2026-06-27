import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output, signal } from '@angular/core';

import { AdminService } from '../../../../core/services/admin.service';

@Component({
  selector: 'app-admin-user-suspend-actions',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './admin-user-suspend-actions.component.html',
  styleUrl: './admin-user-suspend-actions.component.scss',
})
export class AdminUserSuspendActionsComponent {
  @Input() userId: number | null = null;
  @Input() userName = '';
  @Input() userEmail = '';
  @Input() userStatus = 'active';
  @Input() reason = '';
  @Input() compact = false;
  @Input() suspendLabel = 'Suspendre le compte';
  @Input() reactivateLabel = 'Réactiver le compte';
  @Output() changed = new EventEmitter<void>();

  readonly busy = signal(false);

  constructor(private readonly admin: AdminService) {}

  get displayName(): string {
    return this.userName || this.userEmail || 'cet utilisateur';
  }

  suspend(): void {
    if (!this.userId || this.busy()) return;
    const msg = `Suspendre le compte de ${this.displayName} ?\n\nL'utilisateur ne pourra plus utiliser le chat ni l'agent IA.`;
    if (!confirm(msg)) return;
    this.busy.set(true);
    this.admin.suspendUser(this.userId, this.reason).subscribe({
      next: () => {
        this.userStatus = 'suspended';
        this.busy.set(false);
        this.changed.emit();
      },
      error: (err) => {
        this.busy.set(false);
        alert(typeof err.error?.detail === 'string' ? err.error.detail : 'Suspension impossible.');
      },
    });
  }

  reactivate(): void {
    if (!this.userId || this.busy()) return;
    if (!confirm(`Réactiver le compte de ${this.displayName} ?`)) return;
    this.busy.set(true);
    this.admin.reactivateUser(this.userId).subscribe({
      next: () => {
        this.userStatus = 'active';
        this.busy.set(false);
        this.changed.emit();
      },
      error: (err) => {
        this.busy.set(false);
        alert(typeof err.error?.detail === 'string' ? err.error.detail : 'Réactivation impossible.');
      },
    });
  }
}
