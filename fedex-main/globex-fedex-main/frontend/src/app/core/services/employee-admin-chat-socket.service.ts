import { Injectable, OnDestroy } from '@angular/core';
import { Subject } from 'rxjs';

import { API_BASE_URL, AUTH_TOKEN_KEY } from '../api.config';
import { EmployeeAdminMessage } from './employee-portal.service';

export interface AdminChatSocketEvent {
  type: 'message' | 'typing' | 'unread' | 'pong';
  payload?: unknown;
}

@Injectable({ providedIn: 'root' })
export class EmployeeAdminChatSocketService implements OnDestroy {
  private socket: WebSocket | null = null;
  private pingTimer?: ReturnType<typeof setInterval>;
  private readonly events$ = new Subject<AdminChatSocketEvent>();

  readonly stream$ = this.events$.asObservable();

  connect(): void {
    if (this.socket?.readyState === WebSocket.OPEN || this.socket?.readyState === WebSocket.CONNECTING) {
      return;
    }
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    if (!token) return;

    const wsBase = API_BASE_URL.replace(/^http/, 'ws');
    this.socket = new WebSocket(`${wsBase}/api/employee/admin-chat/ws?token=${encodeURIComponent(token)}`);

    this.socket.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data as string) as AdminChatSocketEvent;
        this.events$.next(data);
      } catch {
        /* ignore malformed */
      }
    };

    this.socket.onclose = () => {
      this.clearPing();
      this.socket = null;
    };

    this.socket.onopen = () => {
      this.clearPing();
      this.pingTimer = setInterval(() => this.send({ type: 'ping' }), 25_000);
    };
  }

  disconnect(): void {
    this.clearPing();
    this.socket?.close();
    this.socket = null;
  }

  sendTyping(active: boolean): void {
    this.send({ type: 'typing', payload: { active } });
  }

  ngOnDestroy(): void {
    this.disconnect();
    this.events$.complete();
  }

  private send(data: Record<string, unknown>): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(data));
    }
  }

  private clearPing(): void {
    if (this.pingTimer) {
      clearInterval(this.pingTimer);
      this.pingTimer = undefined;
    }
  }
}

export type AdminChatMessagePayload = EmployeeAdminMessage;
