import { Injectable } from '@angular/core';

import {
  EmployeeAiClientResult,
  EmployeeAiDocumentResult,
  EmployeeAiTicketResult,
  EmployeeAiTrackingResult,
} from './employee-portal.service';

export interface EmployeeAssistantAttachment {
  name: string;
  mimeType: string;
  dataUrl: string;
}

export interface EmployeeAssistantMessage {
  role: 'user' | 'assistant';
  text: string;
  attachments?: EmployeeAssistantAttachment[];
  createdAt: string;
  tracking?: EmployeeAiTrackingResult | null;
  clients?: EmployeeAiClientResult[];
  tickets?: EmployeeAiTicketResult[];
  documents?: EmployeeAiDocumentResult[];
}

export interface EmployeeAssistantSession {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messages: EmployeeAssistantMessage[];
}

const STORAGE_KEY = 'globex_employee_ai_assistant_sessions';

@Injectable({ providedIn: 'root' })
export class EmployeeAiAssistantStateService {
  listSessions(): EmployeeAssistantSession[] {
    return this.readAll().sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  }

  getSession(id: string): EmployeeAssistantSession | null {
    return this.readAll().find((s) => s.id === id) ?? null;
  }

  createSession(title = 'New conversation'): EmployeeAssistantSession {
    const now = new Date().toISOString();
    const session: EmployeeAssistantSession = {
      id: crypto.randomUUID(),
      title,
      createdAt: now,
      updatedAt: now,
      messages: [],
    };
    const all = this.readAll();
    all.unshift(session);
    this.writeAll(all);
    return session;
  }

  saveSession(session: EmployeeAssistantSession): void {
    const all = this.readAll();
    const index = all.findIndex((s) => s.id === session.id);
    session.updatedAt = new Date().toISOString();
    if (index >= 0) {
      all[index] = session;
    } else {
      all.unshift(session);
    }
    this.writeAll(all);
  }

  deleteSession(id: string): void {
    this.writeAll(this.readAll().filter((s) => s.id !== id));
  }

  renameSession(id: string, title: string): void {
    const session = this.getSession(id);
    if (!session) return;
    session.title = title.trim() || session.title;
    this.saveSession(session);
  }

  private readAll(): EmployeeAssistantSession[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw) as EmployeeAssistantSession[];
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }

  private writeAll(sessions: EmployeeAssistantSession[]): void {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  }
}
