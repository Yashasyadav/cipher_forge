import { Injectable, NgZone, OnDestroy } from '@angular/core';
import { BehaviorSubject, Subject } from 'rxjs';

import { environment } from '../../../environments/environment';
import { WipeJobStatus } from '../models/api.models';

@Injectable({ providedIn: 'root' })
export class ProgressWebSocketService implements OnDestroy {
  private readonly updatesSubject = new Subject<Partial<WipeJobStatus> & { jobId: string }>();
  private readonly connectedSubject = new BehaviorSubject<boolean>(false);

  private socket: WebSocket | null = null;
  private reconnectTimerId: number | null = null;
  private manuallyClosed = false;

  readonly updates$ = this.updatesSubject.asObservable();
  readonly connected$ = this.connectedSubject.asObservable();

  constructor(private readonly ngZone: NgZone) {}

  connect(): void {
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.manuallyClosed = false;
    const socket = new WebSocket(this.buildWebSocketUrl());
    this.socket = socket;

    socket.onopen = () => {
      this.connectedSubject.next(true);
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      this.ngZone.run(() => {
        const update = this.parseUpdate(event.data);
        if (update) {
          this.updatesSubject.next(update);
        }
      });
    };

    socket.onerror = () => {
      this.connectedSubject.next(false);
    };

    socket.onclose = () => {
      this.connectedSubject.next(false);
      this.socket = null;
      if (!this.manuallyClosed) {
        this.scheduleReconnect();
      }
    };
  }

  disconnect(): void {
    this.manuallyClosed = true;
    this.clearReconnectTimer();
    this.connectedSubject.next(false);
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  ngOnDestroy(): void {
    this.disconnect();
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimerId !== null) {
      return;
    }
    this.reconnectTimerId = window.setTimeout(() => {
      this.reconnectTimerId = null;
      this.connect();
    }, 3000);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimerId !== null) {
      window.clearTimeout(this.reconnectTimerId);
      this.reconnectTimerId = null;
    }
  }

  private buildWebSocketUrl(): string {
    const baseUrl = new URL(environment.apiBaseUrl);
    const wsProtocol = baseUrl.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${wsProtocol}//${baseUrl.host}/ws/progress`;
  }

  private parseUpdate(payload: string): (Partial<WipeJobStatus> & { jobId: string }) | null {
    try {
      const parsed = JSON.parse(payload) as Record<string, unknown>;
      const jobId = this.readString(parsed, ['jobId', 'job_id']);
      if (!jobId) {
        return null;
      }

      return {
        jobId,
        engineJobId: this.readString(parsed, ['engineJobId', 'engine_job_id']) ?? undefined,
        device: this.readString(parsed, ['device']) ?? undefined,
        wipeMethod: this.readString(parsed, ['wipeMethod', 'wipe_method']) ?? undefined,
        status: this.readString(parsed, ['status']) ?? undefined,
        progress: this.readNumber(parsed, ['progress']),
        startTime: this.readString(parsed, ['startTime', 'start_time']) ?? undefined,
        endTime: this.readString(parsed, ['endTime', 'end_time']) ?? undefined,
        certificateId: this.readString(parsed, ['certificateId', 'certificate_id']) ?? undefined,
        error: this.readString(parsed, ['error']) ?? undefined
      };
    } catch {
      return null;
    }
  }

  private readString(source: Record<string, unknown>, keys: string[]): string | null {
    for (const key of keys) {
      const value = source[key];
      if (typeof value === 'string' && value.trim()) {
        return value;
      }
    }
    return null;
  }

  private readNumber(source: Record<string, unknown>, keys: string[]): number | undefined {
    for (const key of keys) {
      const value = source[key];
      if (typeof value === 'number' && Number.isFinite(value)) {
        return value;
      }
      if (typeof value === 'string') {
        const parsed = Number(value);
        if (!Number.isNaN(parsed) && Number.isFinite(parsed)) {
          return parsed;
        }
      }
    }
    return undefined;
  }
}
