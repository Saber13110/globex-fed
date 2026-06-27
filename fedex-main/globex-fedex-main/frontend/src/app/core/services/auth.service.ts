import { HttpClient } from '@angular/common/http';
import { Injectable, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';

import { API_BASE_URL, AUTH_TOKEN_KEY } from '../api.config';

export interface RegisterPayload {
  full_name: string;
  email: string;
  password: string;
  preferred_language?: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface LoginResponse {
  access_token?: string | null;
  token_type?: string;
  requires_2fa: boolean;
  challenge_token?: string | null;
  masked_email?: string | null;
  detail?: string | null;
}

export interface GoogleAuthConfigResponse {
  enabled: boolean;
  client_id?: string | null;
}

export interface GoogleLoginPayload {
  id_token: string;
  nonce?: string;
}

export interface AuthUserProfile {
  id: number;
  full_name: string;
  email: string;
  role: string;
  preferred_language?: string | null;
  response_preferences?: string | null;
}

export type PreferenceTone = 'professional' | 'friendly' | 'concise' | 'formal';

export interface PreferenceProfileStructured {
  tone: PreferenceTone;
  cite_fedex: boolean;
  short_answers: boolean;
  free_notes: string;
}

export interface PreferenceSubmitPayload {
  tone?: PreferenceTone;
  cite_fedex?: boolean;
  short_answers?: boolean;
  free_notes?: string;
  proposed_text?: string;
}

export interface UserPreferencesState {
  active: string;
  active_structured?: PreferenceProfileStructured | null;
  pending: string | null;
  pending_structured?: PreferenceProfileStructured | null;
  pending_id: number | null;
  pending_status: string | null;
  pending_risk_score: number | null;
  pending_risk_reasons: string[];
  rejection_note: string | null;
  submitted_at: string | null;
}

export interface ActiveSession {
  id: number;
  browser: string;
  machine: string;
  location: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface AccountOverviewResponse {
  user_id: number;
  organization_id: string;
  sessions: ActiveSession[];
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  readonly token = signal<string | null>(localStorage.getItem(AUTH_TOKEN_KEY));

  constructor(
    private readonly http: HttpClient,
    private readonly router: Router,
  ) {}

  register(payload: RegisterPayload): Observable<unknown> {
    return this.http.post(`${API_BASE_URL}/auth/register`, {
      ...payload,
      preferred_language: payload.preferred_language ?? 'fr',
    });
  }

  registerEmployee(payload: RegisterPayload): Observable<{ detail: string; email: string; status: string }> {
    return this.http.post<{ detail: string; email: string; status: string }>(
      `${API_BASE_URL}/auth/register/employee`,
      { ...payload, preferred_language: payload.preferred_language ?? 'fr' },
    );
  }

  activate(token: string): Observable<unknown> {
    return this.http.post(`${API_BASE_URL}/auth/activate`, { token });
  }

  login(payload: LoginPayload): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${API_BASE_URL}/auth/login`, payload);
  }

  googleConfig(): Observable<GoogleAuthConfigResponse> {
    return this.http.get<GoogleAuthConfigResponse>(`${API_BASE_URL}/auth/google/config`);
  }

  loginWithGoogle(payload: GoogleLoginPayload): Observable<TokenResponse> {
    return this.http
      .post<TokenResponse>(`${API_BASE_URL}/auth/google`, payload)
      .pipe(tap((res) => this.persistToken(res.access_token)));
  }

  verify2fa(challengeToken: string, code: string): Observable<TokenResponse> {
    return this.http
      .post<TokenResponse>(`${API_BASE_URL}/auth/2fa/verify`, {
        challenge_token: challengeToken,
        code,
      })
      .pipe(tap((res) => this.persistToken(res.access_token)));
  }

  resend2fa(challengeToken: string): Observable<{ detail: string }> {
    return this.http.post<{ detail: string }>(`${API_BASE_URL}/auth/2fa/resend`, {
      challenge_token: challengeToken,
    });
  }

  getMyQrLogin(): Observable<{ payload: string | null; has_active_qr: boolean; can_use_qr: boolean }> {
    return this.http.get<{ payload: string | null; has_active_qr: boolean; can_use_qr: boolean }>(
      `${API_BASE_URL}/auth/me/qr-login`,
    );
  }

  regenerateMyQrLogin(): Observable<{ payload: string | null; has_active_qr: boolean; can_use_qr: boolean }> {
    return this.http.post<{ payload: string | null; has_active_qr: boolean; can_use_qr: boolean }>(
      `${API_BASE_URL}/auth/me/qr-login/regenerate`,
      {},
    );
  }

  loginWithQr(payload: string): Observable<TokenResponse> {
    return this.http
      .post<TokenResponse>(`${API_BASE_URL}/auth/qr-login`, { payload })
      .pipe(tap((res) => this.persistToken(res.access_token)));
  }

  me(): Observable<AuthUserProfile> {
    return this.http.get<AuthUserProfile>(`${API_BASE_URL}/auth/me`);
  }

  updateProfile(payload: {
    preferred_language?: string;
    response_preferences?: string;
  }): Observable<AuthUserProfile> {
    return this.http.patch<AuthUserProfile>(`${API_BASE_URL}/auth/me`, payload);
  }

  getMyPreferences(): Observable<UserPreferencesState> {
    return this.http.get<UserPreferencesState>(`${API_BASE_URL}/auth/me/preferences`);
  }

  submitPreferences(payload: PreferenceSubmitPayload): Observable<UserPreferencesState> {
    return this.http.post<UserPreferencesState>(`${API_BASE_URL}/auth/me/preferences/submit`, payload);
  }

  accountOverview(): Observable<AccountOverviewResponse> {
    return this.http.get<AccountOverviewResponse>(`${API_BASE_URL}/auth/account-overview`);
  }

  logoutAll(): Observable<void> {
    return this.http.post<void>(`${API_BASE_URL}/auth/logout-all`, {});
  }

  deleteAccount(): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/auth/account`);
  }

  clearLocalSession(): void {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    this.token.set(null);
  }

  logout(): void {
    this.clearLocalSession();
    void this.router.navigateByUrl('/login');
  }

  persistTokenFromLogin(accessToken: string): void {
    this.persistToken(accessToken);
  }

  private persistToken(accessToken: string): void {
    localStorage.setItem(AUTH_TOKEN_KEY, accessToken);
    this.token.set(accessToken);
  }
}
