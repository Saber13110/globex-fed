import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { AuthService } from '../../../core/services/auth.service';
import { I18nService } from '../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../core/i18n/translate.pipe';
import { UserPreferencesService } from '../../../core/services/user-preferences.service';
import { QrScannerComponent } from '../qr-scanner/qr-scanner.component';

type LoginStep = 'credentials' | 'otp';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, FormsModule, RouterLink, QrScannerComponent, TranslatePipe],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent implements OnInit {
  step: LoginStep = 'credentials';
  challengeToken: string | null = null;
  maskedEmail: string | null = null;
  resendCooldown = false;

  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required]],
  });

  readonly otpForm = this.fb.nonNullable.group({
    code: ['', [Validators.required, Validators.pattern(/^\d{6}$/)]],
  });

  error: string | null = null;
  info: string | null = null;
  loading = false;
  showPassword = false;
  showQrScanner = false;
  manualQrPayload = '';
  googleEnabled = false;
  googleClientId: string | null = null;

  readonly isEmployee = this.route.snapshot.data['audience'] === 'employee';

  constructor(
    private readonly fb: FormBuilder,
    private readonly auth: AuthService,
    private readonly i18n: I18nService,
    private readonly prefs: UserPreferencesService,
    private readonly router: Router,
    private readonly route: ActivatedRoute,
  ) {}

  ngOnInit(): void {
    this.auth.googleConfig().subscribe({
      next: (cfg) => {
        this.googleEnabled = !!cfg.enabled && !!cfg.client_id;
        this.googleClientId = cfg.client_id ?? null;
      },
    });
    this.handleGoogleCallback();
  }

  togglePassword(): void {
    this.showPassword = !this.showPassword;
  }

  onForgotPassword(): void {
    this.error = null;
    this.info = this.i18n.t('auth.login.forgotPasswordHint');
  }

  fieldInvalid(name: 'email' | 'password'): boolean {
    const ctrl = this.form.get(name);
    return !!(ctrl && ctrl.invalid && (ctrl.touched || ctrl.dirty));
  }

  fieldError(name: 'email' | 'password'): string {
    const ctrl = this.form.get(name);
    if (!ctrl?.errors) return 'auth.login.fieldRequired';
    if (ctrl.errors['email']) return 'auth.login.emailInvalid';
    return 'auth.login.fieldRequired';
  }

  otpFieldInvalid(): boolean {
    const ctrl = this.otpForm.get('code');
    return !!(ctrl && ctrl.invalid && (ctrl.touched || ctrl.dirty));
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.error = null;
    this.info = null;
    this.loading = true;
    this.auth.login(this.form.getRawValue()).subscribe({
      next: (res) => {
        this.loading = false;
        if (res.requires_2fa && res.challenge_token) {
          this.step = 'otp';
          this.challengeToken = res.challenge_token;
          this.maskedEmail = res.masked_email ?? null;
          this.info = res.detail ?? this.i18n.t('auth.login.otpSent');
          return;
        }
        if (res.access_token) {
          this.auth.persistTokenFromLogin(res.access_token);
          this.finishLogin();
        }
      },
      error: (err) => {
        this.loading = false;
        const detail = err?.error?.detail;
        this.error = typeof detail === 'string' ? detail : this.i18n.t('auth.login.error');
      },
    });
  }

  submitOtp(): void {
    if (this.otpForm.invalid || !this.challengeToken) {
      this.otpForm.markAllAsTouched();
      return;
    }
    this.error = null;
    this.loading = true;
    this.auth.verify2fa(this.challengeToken, this.otpForm.getRawValue().code).subscribe({
      next: () => {
        this.loading = false;
        this.finishLogin();
      },
      error: (err) => {
        this.loading = false;
        const detail = err?.error?.detail;
        this.error = typeof detail === 'string' ? detail : this.i18n.t('auth.login.wrongCode');
        if (err?.status === 410 || err?.status === 429) {
          this.backToCredentials();
        }
      },
    });
  }

  resendCode(): void {
    if (!this.challengeToken || this.resendCooldown) {
      return;
    }
    this.error = null;
    this.auth.resend2fa(this.challengeToken).subscribe({
      next: (res) => {
        this.info = res.detail;
        this.resendCooldown = true;
        setTimeout(() => (this.resendCooldown = false), 60_000);
      },
      error: (err) => {
        const detail = err?.error?.detail;
        this.error = typeof detail === 'string' ? detail : this.i18n.t('auth.login.resendFailed');
        if (err?.status === 410 || err?.status === 429) {
          this.backToCredentials();
        }
      },
    });
  }

  backToCredentials(): void {
    this.step = 'credentials';
    this.challengeToken = null;
    this.maskedEmail = null;
    this.otpForm.reset();
    this.error = null;
    this.info = null;
    this.showQrScanner = false;
  }

  openQrScanner(): void {
    this.error = null;
    this.showQrScanner = true;
  }

  closeQrScanner(): void {
    this.showQrScanner = false;
  }

  onQrScanned(payload: string): void {
    this.showQrScanner = false;
    this.loginWithQrPayload(payload);
  }

  submitManualQr(): void {
    const payload = this.manualQrPayload.trim();
    if (!payload) {
      return;
    }
    this.loginWithQrPayload(payload);
  }

  private loginWithQrPayload(payload: string): void {
    this.error = null;
    this.loading = true;
    this.auth.loginWithQr(payload).subscribe({
      next: () => {
        this.loading = false;
        this.finishLogin();
      },
      error: (err) => {
        this.loading = false;
        const detail = err?.error?.detail;
        this.error = typeof detail === 'string' ? detail : this.i18n.t('auth.login.invalidQr');
      },
    });
  }

  startGoogleLogin(): void {
    if (!this.googleEnabled || !this.googleClientId || this.isEmployee) {
      return;
    }
    const nonce = crypto.randomUUID();
    sessionStorage.setItem('google_oauth_nonce', nonce);
    const redirectUri = `${window.location.origin}/login`;
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
      next: () => {
        sessionStorage.removeItem('google_oauth_nonce');
        this.loading = false;
        this.finishLogin();
      },
      error: (err) => {
        sessionStorage.removeItem('google_oauth_nonce');
        this.loading = false;
        const detail = err?.error?.detail;
        this.error = typeof detail === 'string' ? detail : this.i18n.t('auth.login.googleError');
      },
    });
  }

  private finishLogin(): void {
    this.auth.me().subscribe({
      next: async (profile) => {
        const role = profile.role;
        const wrongSpace =
          (this.isEmployee && role === 'client') || (!this.isEmployee && role === 'employe');
        if (wrongSpace) {
          this.auth.clearLocalSession();
          this.loading = false;
          this.backToCredentials();
          this.error = this.isEmployee
            ? this.i18n.t('auth.login.wrongSpaceEmployee')
            : this.i18n.t('auth.login.wrongSpaceClient');
          return;
        }
        this.prefs.syncFromAuthProfile(profile);
        this.i18n.syncFromAuthProfile(profile.preferred_language);
        this.loading = false;
        if (role === 'admin') {
          await this.router.navigateByUrl('/admin');
        } else if (role === 'employe') {
          await this.router.navigateByUrl('/employee');
        } else {
          await this.router.navigateByUrl('/chat');
        }
      },
      error: () => {
        this.auth.clearLocalSession();
        this.loading = false;
        this.error = this.i18n.t('auth.login.error');
      },
    });
  }
}
