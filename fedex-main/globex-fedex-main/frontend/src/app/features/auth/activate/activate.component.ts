import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { AuthService } from '../../../core/services/auth.service';

@Component({
  selector: 'app-activate',
  standalone: true,
  imports: [CommonModule, RouterLink],
  templateUrl: './activate.component.html',
  styleUrl: '../login/login.component.scss',
})
export class ActivateComponent implements OnInit {
  state: 'loading' | 'success' | 'error' = 'loading';
  message = '';

  constructor(
    private readonly route: ActivatedRoute,
    private readonly auth: AuthService,
  ) {}

  ngOnInit(): void {
    const token = this.route.snapshot.queryParamMap.get('token') ?? '';
    if (!token) {
      this.state = 'error';
      this.message = "Lien d'activation invalide : token manquant.";
      return;
    }
    this.auth.activate(token).subscribe({
      next: () => {
        this.state = 'success';
        this.message = 'Votre compte a été activé. Vous pouvez maintenant vous connecter.';
      },
      error: (err) => {
        this.state = 'error';
        const detail = err?.error?.detail;
        this.message = typeof detail === 'string' ? detail : "Échec de l'activation du compte.";
      },
    });
  }
}
