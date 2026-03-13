import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { AuthService } from '../services/auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const token = authService.getToken();

  const isLoginRequest = req.url.includes('/auth/login');

  if (!token || isLoginRequest) {
    return next(req).pipe(
      catchError((error) => {
        if (!isLoginRequest && error?.status === 401) {
          authService.logout();
          void router.navigate(['/login']);
        }
        return throwError(() => error);
      })
    );
  }

  const authReq = req.clone({
    setHeaders: {
      Authorization: `Bearer ${token}`
    }
  });
  return next(authReq).pipe(
    catchError((error) => {
      if (error?.status === 401) {
        authService.logout();
        void router.navigate(['/login']);
      }
      return throwError(() => error);
    })
  );
};
