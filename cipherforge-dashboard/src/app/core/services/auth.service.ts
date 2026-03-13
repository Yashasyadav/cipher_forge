import { Injectable } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Observable, catchError, tap, throwError } from 'rxjs';

import { environment } from '../../../environments/environment';
import { AuthLoginRequest, AuthResponse, UserRole } from '../models/api.models';

type StoredSession = Pick<AuthResponse, 'token' | 'username' | 'role'>;

@Injectable({ providedIn: 'root' })
export class AuthService {
  private static readonly sessionStorageKey = 'cipherforge_auth_session';

  constructor(private readonly http: HttpClient) {}

  login(request: AuthLoginRequest): Observable<AuthResponse> {
    return this.http.post<AuthResponse>(`${environment.apiBaseUrl}/auth/login`, request).pipe(
      tap((response) => this.setSession(response)),
      catchError((error: HttpErrorResponse) => {
        if (error.status === 401) {
          return throwError(() => new Error('Invalid username or password.'));
        }
        if (error.status === 0) {
          return throwError(() => new Error('Backend is not reachable. Start the Spring Boot server and try again.'));
        }
        const backendMessage =
          typeof error.error === 'object' && error.error && 'message' in error.error
            ? String((error.error as { message?: unknown }).message ?? '')
            : '';
        const message = backendMessage.trim() || 'Login failed. Please try again.';
        return throwError(() => new Error(message));
      })
    );
  }

  logout(): void {
    localStorage.removeItem(AuthService.sessionStorageKey);
  }

  isAuthenticated(): boolean {
    const token = this.getToken();
    if (!token) {
      return false;
    }

    const payload = this.parseJwtPayload(token);
    if (!payload) {
      return false;
    }

    const exp = payload?.['exp'];
    if (typeof exp !== 'number') {
      return false;
    }

    return Date.now() < exp * 1000;
  }

  getToken(): string | null {
    return this.getSession()?.token ?? null;
  }

  getUsername(): string | null {
    return this.getSession()?.username ?? null;
  }

  getRole(): UserRole | null {
    return this.getSession()?.role ?? null;
  }

  hasAnyRole(...roles: UserRole[]): boolean {
    const role = this.getRole();
    return role !== null && roles.includes(role);
  }

  private setSession(response: AuthResponse): void {
    const session: StoredSession = {
      token: response.token,
      username: response.username,
      role: response.role
    };
    localStorage.setItem(AuthService.sessionStorageKey, JSON.stringify(session));
  }

  private getSession(): StoredSession | null {
    const raw = localStorage.getItem(AuthService.sessionStorageKey);
    if (!raw) {
      return null;
    }
    try {
      return JSON.parse(raw) as StoredSession;
    } catch {
      return null;
    }
  }

  private parseJwtPayload(token: string): Record<string, unknown> | null {
    const segments = token.split('.');
    if (segments.length < 2) {
      return null;
    }

    const payloadSegment = segments[1].replace(/-/g, '+').replace(/_/g, '/');
    const paddedSegment = payloadSegment.padEnd(Math.ceil(payloadSegment.length / 4) * 4, '=');
    try {
      const decoded = atob(paddedSegment);
      return JSON.parse(decoded) as Record<string, unknown>;
    } catch {
      return null;
    }
  }
}
