import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { API_BASE_URL, AUTH_TOKEN_KEY } from '../api.config';
import { AuthService } from '../services/auth.service';

function isGuestRoute(url: string): boolean {
  return (
    url.startsWith('/login') ||
    url.startsWith('/register') ||
    url.startsWith('/employee/login') ||
    url.startsWith('/employee/register') ||
    url.startsWith('/employee/activate')
  );
}

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);
  const auth = inject(AuthService);
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  const isApi = req.url.startsWith(API_BASE_URL);
  const isAuthEndpoint =
    req.url.includes('/auth/login') ||
    req.url.includes('/auth/register') ||
    req.url.includes('/auth/2fa/') ||
    req.url.includes('/auth/qr-login');
  const isSessionProbe = req.url.includes('/auth/me');

  if (isApi && token) {
    req = req.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
  }

  return next(req).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse && isApi && !isAuthEndpoint) {
        // Déconnexion uniquement sur 401 explicite (pas sur erreurs réseau/CORS status 0).
        if (error.status === 401) {
          auth.clearLocalSession();
          // /auth/me et les pages invitées : les guards gèrent la redirection.
          if (!isSessionProbe && !isGuestRoute(router.url)) {
            const loginUrl = router.url.startsWith('/employee') ? '/employee/login' : '/login';
            void router.navigateByUrl(loginUrl);
          }
        }
      }
      return throwError(() => error);
    }),
  );
};
