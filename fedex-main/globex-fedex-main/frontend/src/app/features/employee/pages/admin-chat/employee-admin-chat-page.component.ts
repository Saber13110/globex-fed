import { CommonModule } from '@angular/common';
import { Component, ElementRef, HostListener, OnDestroy, OnInit, ViewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import {
  LucideFileText,
  LucidePaperclip,
  LucideSearch,
  LucideSend,
  LucideX,
  provideLucideIcons,
} from '@lucide/angular';
import { Subject, Subscription, debounceTime, distinctUntilChanged } from 'rxjs';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import {
  AdminChatMessagePayload,
  AdminChatSocketEvent,
  EmployeeAdminChatSocketService,
} from '../../../../core/services/employee-admin-chat-socket.service';
import { EmployeeAdminCommsStateService } from '../../../../core/services/employee-admin-comms-state.service';
import {
  EmployeeAdminChatParticipant,
  EmployeeAdminChatSearchHit,
  EmployeeAdminChatWorkspace,
  EmployeeAdminMessage,
  EmployeePortalService,
} from '../../../../core/services/employee-portal.service';
import { SupportService } from '../../../../core/services/support.service';

@Component({
  selector: 'app-employee-admin-chat-page',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslatePipe, LucideSearch, LucidePaperclip, LucideSend, LucideFileText, LucideX],
  providers: [provideLucideIcons(LucideSearch, LucidePaperclip, LucideSend, LucideFileText, LucideX)],
  templateUrl: './employee-admin-chat-page.component.html',
  styleUrl: './employee-admin-chat-page.component.scss',
})
export class EmployeeAdminChatPageComponent implements OnInit, OnDestroy {
  @ViewChild('threadEl') threadEl?: ElementRef<HTMLDivElement>;
  @ViewChild('composerEl') composerEl?: ElementRef<HTMLTextAreaElement>;

  workspace: EmployeeAdminChatWorkspace | null = null;
  messages: EmployeeAdminMessage[] = [];
  adminContact: EmployeeAdminChatParticipant | null = null;
  sharedFiles: EmployeeAdminChatWorkspace['shared_files'] = [];

  draft = '';
  searchQ = '';
  searchHits: EmployeeAdminChatSearchHit[] = [];
  showSearch = false;
  searching = false;
  sending = false;
  uploading = false;
  typingLabel = '';
  highlightMessageId: number | null = null;

  pendingFile: File | null = null;
  pendingFilePreview: string | null = null;

  private socketSub?: Subscription;
  private typingTimer?: ReturnType<typeof setTimeout>;
  private typingStopTimer?: ReturnType<typeof setTimeout>;
  private readonly search$ = new Subject<string>();
  private searchSub?: Subscription;

  constructor(
    private readonly employee: EmployeePortalService,
    private readonly support: SupportService,
    private readonly socket: EmployeeAdminChatSocketService,
    private readonly commsState: EmployeeAdminCommsStateService,
    private readonly route: ActivatedRoute,
  ) {}

  ngOnInit(): void {
    const draft = this.route.snapshot.queryParamMap.get('draft');
    if (draft) this.draft = draft;

    this.loadWorkspace();
    this.socket.connect();
    this.socketSub = this.socket.stream$.subscribe((ev) => this.onSocketEvent(ev));

    this.searchSub = this.search$
      .pipe(debounceTime(280), distinctUntilChanged())
      .subscribe((term) => {
        const q = term.trim();
        if (q.length < 2) {
          this.searchHits = [];
          this.searching = false;
          return;
        }
        this.searching = true;
        this.employee.searchAdminChat(q).subscribe({
          next: (res) => {
            this.searchHits = res.items;
            this.searching = false;
          },
          error: () => (this.searching = false),
        });
      });
  }

  ngOnDestroy(): void {
    this.socketSub?.unsubscribe();
    this.searchSub?.unsubscribe();
    this.socket.disconnect();
    if (this.typingTimer) clearTimeout(this.typingTimer);
    if (this.typingStopTimer) clearTimeout(this.typingStopTimer);
    this.clearPendingFile();
  }

  @HostListener('document:keydown', ['$event'])
  handleShortcut(event: KeyboardEvent): void {
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault();
      this.send();
    }
  }

  loadWorkspace(): void {
    this.employee.getAdminChatWorkspace().subscribe({
      next: (ws) => {
        this.workspace = ws;
        this.messages = ws.messages;
        this.adminContact = ws.participants.find((p) => p.id === 'administrator') ?? ws.participants[0] ?? null;
        this.sharedFiles = ws.shared_files;
        this.commsState.setUnread(ws.unread_count);
        if (ws.unread_count > 0) {
          this.employee.markAdminChatRead().subscribe({
            next: () => this.commsState.setUnread(0),
          });
        }
        setTimeout(() => this.scrollThread(), 50);
      },
    });
  }

  onSearchInput(): void {
    this.showSearch = this.searchQ.trim().length > 0;
    this.search$.next(this.searchQ);
  }

  clearSearch(): void {
    this.searchQ = '';
    this.searchHits = [];
    this.showSearch = false;
  }

  openSearchHit(hit: EmployeeAdminChatSearchHit): void {
    this.clearSearch();
    if (hit.message_id) {
      this.highlightMessageId = hit.message_id;
      setTimeout(() => {
        document.getElementById(`admin-msg-${hit.message_id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 80);
    }
  }

  onDraftInput(): void {
    this.socket.sendTyping(true);
    this.employee.sendAdminTyping(true).subscribe();
    if (this.typingStopTimer) clearTimeout(this.typingStopTimer);
    this.typingStopTimer = setTimeout(() => {
      this.socket.sendTyping(false);
      this.employee.sendAdminTyping(false).subscribe();
    }, 1200);
  }

  onPaste(event: ClipboardEvent): void {
    const items = event.clipboardData?.items;
    if (!items) return;
    for (const item of Array.from(items)) {
      if (item.type.startsWith('image/')) {
        event.preventDefault();
        const file = item.getAsFile();
        if (file) this.setPendingFile(file);
        return;
      }
    }
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) this.setPendingFile(file);
    input.value = '';
  }

  setPendingFile(file: File): void {
    this.clearPendingFile();
    this.pendingFile = file;
    if (file.type.startsWith('image/')) {
      this.pendingFilePreview = URL.createObjectURL(file);
    }
  }

  clearPendingFile(): void {
    if (this.pendingFilePreview) URL.revokeObjectURL(this.pendingFilePreview);
    this.pendingFile = null;
    this.pendingFilePreview = null;
  }

  send(): void {
    const body = this.draft.trim();
    if (this.pendingFile) {
      this.uploadAndSend(body || this.pendingFile.name);
      return;
    }
    if (!body || this.sending) return;
    this.sending = true;
    this.employee.sendAdminMessage(body).subscribe({
      next: (msg) => {
        this.messages = [...this.messages, msg];
        this.draft = '';
        this.sending = false;
        this.scrollThread();
        this.touchActivity(msg);
      },
      error: () => (this.sending = false),
    });
  }

  uploadAndSend(body: string): void {
    if (!this.pendingFile || this.uploading) return;
    const file = this.pendingFile;
    this.uploading = true;
    this.support.uploadAttachment(file).subscribe({
      next: (res) => {
        this.employee.sendAdminMessage(body, res.url).subscribe({
          next: (msg) => {
            this.messages = [...this.messages, msg];
            this.draft = '';
            this.clearPendingFile();
            this.uploading = false;
            this.scrollThread();
            this.touchActivity(msg);
          },
          error: () => (this.uploading = false),
        });
      },
      error: () => (this.uploading = false),
    });
  }

  openAttachment(url: string): void {
    this.support.openAttachment(url).subscribe({
      error: () => window.alert('Impossible d\'ouvrir la pièce jointe.'),
    });
  }

  isMine(msg: EmployeeAdminMessage): boolean {
    return msg.sender_role === 'employe' || msg.sender_role === 'employee';
  }

  msgWrapperClass(msg: EmployeeAdminMessage): string {
    return this.isMine(msg) ? 'acomms-msg acomms-msg--mine' : 'acomms-msg acomms-msg--admin';
  }

  msgRoleKey(msg: EmployeeAdminMessage): string {
    return this.isMine(msg) ? 'employee.comms.roleYou' : 'employee.comms.roleAdmin';
  }

  formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
  }

  formatTime(iso: string): string {
    return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  }

  formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  groupLabel(index: number): string | null {
    if (index === 0) return this.formatDate(this.messages[index].created_at);
    const prev = new Date(this.messages[index - 1].created_at).toDateString();
    const cur = new Date(this.messages[index].created_at).toDateString();
    return prev !== cur ? this.formatDate(this.messages[index].created_at) : null;
  }

  private onSocketEvent(ev: AdminChatSocketEvent): void {
    if (ev.type === 'message') {
      const msg = ev.payload as AdminChatMessagePayload;
      if (!this.messages.some((m) => m.id === msg.id)) {
        this.messages = [...this.messages, msg];
        this.touchActivity(msg);
        this.scrollThread();
      }
      if (msg.sender_role === 'admin') {
        this.employee.markAdminChatRead().subscribe();
        this.commsState.setUnread(0);
      }
    } else if (ev.type === 'unread') {
      const payload = ev.payload as { count?: number };
      if (typeof payload?.count === 'number') {
        this.commsState.setUnread(payload.count);
      }
    } else if (ev.type === 'typing') {
      const payload = ev.payload as { sender_role?: string; sender_name?: string; active?: boolean };
      if (payload?.active && payload.sender_role === 'admin') {
        this.typingLabel = payload.sender_name || 'Admin';
        if (this.typingTimer) clearTimeout(this.typingTimer);
        this.typingTimer = setTimeout(() => (this.typingLabel = ''), 4000);
      } else {
        this.typingLabel = '';
      }
    }
  }

  private touchActivity(msg: EmployeeAdminMessage): void {
    if (this.workspace) {
      this.workspace = { ...this.workspace, last_activity_at: msg.created_at };
    }
  }

  private scrollThread(): void {
    const el = this.threadEl?.nativeElement;
    if (el) el.scrollTop = el.scrollHeight;
  }
}
