import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import {
  AbstractControl,
  FormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { AuthService } from '../../../core/services/auth.service';
import { I18nService } from '../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../core/i18n/translate.pipe';

type RegisterField = 'full_name' | 'email' | 'password' | 'password_confirm';

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, RouterLink, TranslatePipe],
  templateUrl: './register.component.html',
  styleUrl: './register.component.scss',
})
export class RegisterComponent implements OnInit {
  readonly isEmployee = this.route.snapshot.data['audience'] === 'employee';

  readonly form = this.fb.nonNullable.group(
    {
      full_name: ['', [Validators.required, Validators.maxLength(255)]],
      email: ['', [Validators.required, Validators.email]],
      password: ['', [Validators.required, Validators.minLength(8), Validators.maxLength(128)]],
      password_confirm: ['', [Validators.required]],
    },
    { validators: [RegisterComponent.passwordsMatch] },
  );

  error: string | null = null;
  loading = false;
  pendingMessage: string | null = null;
  googleEnabled = false;
  googleClientId: string | null = null;
  showPassword = false;
  showPasswordConfirm = false;

  constructor(
    private readonly fb: FormBuilder,
    private readonly auth: AuthService,
    private readonly i18n: I18nService,
    private readonly router: Router,
    private readonly route: ActivatedRoute,
  ) {}

  private static passwordsMatch(group: AbstractControl): ValidationErrors | null {
    const password = group.get('password')?.value;
    const confirm = group.get('password_confirm')?.value;
    if (!confirm) {
      return null;
    }
    return password === confirm ? null : { passwordMismatch: true };
  }

  ngOnInit(): void {
    this.auth.googleConfig().subscribe({
      next: (cfg) => {
        this.googleEnabled = !!cfg.enabled && !!cfg.client_id;
        this.googleClientId = cfg.client_id ?? null;
      },
    });
    this.handleGoogleCallback();
    this.form.get('password')?.valueChanges.subscribe(() => {
      this.form.get('password_confirm')?.updateValueAndValidity({ emitEvent: false });
      this.form.updateValueAndValidity({ emitEvent: false });
    });
  }

  togglePassword(): void {
    this.showPassword = !this.showPassword;
  }

  togglePasswordConfirm(): void {
    this.showPasswordConfirm = !this.showPasswordConfirm;
  }

  fieldInvalid(name: RegisterField): boolean {
    const ctrl = this.form.get(name);
    if (!ctrl) {
      return false;
    }
    if (name === 'password_confirm' && this.passwordMismatch && (ctrl.touched || ctrl.dirty)) {
      return true;
    }
    return !!(ctrl.invalid && (ctrl.touched || ctrl.dirty));
  }

  get passwordMismatch(): boolean {
    return !!this.form.errors?.['passwordMismatch'];
  }

  fieldError(name: RegisterField): string {
    const ctrl = this.form.get(name);
    if (name === 'password_confirm') {
      if (this.passwordMismatch && (ctrl?.touched || ctrl?.dirty)) {
        return 'auth.register.passwordMismatch';
      }
      if (ctrl?.errors?.['required']) {
        return 'auth.register.fieldRequired';
      }
    }
    if (!ctrl?.errors) {
      return 'auth.register.fieldRequired';
    }
    if (ctrl.errors['email']) {
      return 'auth.register.emailInvalid';
    }
    if (ctrl.errors['minlength']) {
      return 'auth.register.passwordMin';
    }
    if (ctrl.errors['required']) {
      return 'auth.register.fieldRequired';
    }
    return 'auth.register.fieldRequired';
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.error = null;
    this.loading = true;

    const { full_name, email, password } = this.form.getRawValue();

    if (this.isEmployee) {
      this.auth
        .registerEmployee({
          full_name,
          email,
          password,
          preferred_language: this.i18n.toBackendCode(),
        })
        .subscribe({
          next: (res) => {
            this.loading = false;
            this.pendingMessage = res.detail;
          },
          error: (err) => {
            this.loading = false;
            const detail = err?.error?.detail;
            this.error = typeof detail === 'string' ? detail : this.i18n.t('auth.register.error');
          },
        });
      return;
    }

    this.auth
      .register({
        full_name,
        email,
        password,
        preferred_language: this.i18n.toBackendCode(),
      })
      .subscribe({
        next: async () => {
          this.loading = false;
          await this.router.navigateByUrl('/login');
        },
        error: (err) => {
          this.loading = false;
          const detail = err?.error?.detail;
          this.error = typeof detail === 'string' ? detail : this.i18n.t('auth.register.error');
        },
      });
  }

  startGoogleRegister(): void {
    if (!this.googleEnabled || !this.googleClientId || this.isEmployee) {
      return;
    }
    const nonce = crypto.randomUUID();
    sessionStorage.setItem('google_oauth_nonce', nonce);
    const redirectUri = `${window.location.origin}/register`;
    const params = new URLSearchParams({
      client_id: this.googleClientId,
      redirect_uri: redirectUri,
      response_type: 'id_token',
      scope: 'openid email profile',
      nonce,
      prompt: 'select_account',
    });
    window.location.assign(`https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`);
  }

  private handleGoogleCallback(): void {
    if (this.isEmployee) {
      return;
    }
    const hash = window.location.hash.startsWith('#') ? window.location.hash.slice(1) : '';
    if (!hash.includes('id_token=')) {
      return;
    }
    const params = new URLSearchParams(hash);
    const idToken = params.get('id_token');
    const nonce = sessionStorage.getItem('google_oauth_nonce') ?? undefined;
    window.history.replaceState({}, document.title, window.location.pathname);
    if (!idToken) {
      return;
    }
    this.loading = true;
    this.auth.loginWithGoogle({ id_token: idToken, nonce }).subscribe({
      next: async () => {
        sessionStorage.removeItem('google_oauth_nonce');
        this.loading = false;
        await this.router.navigateByUrl('/chat');
      },
      error: (err) => {
        sessionStorage.removeItem('google_oauth_nonce');
        this.loading = false;
        const detail = err?.error?.detail;
        this.error = typeof detail === 'string' ? detail : this.i18n.t('auth.register.googleError');
      },
    });
  }
}
