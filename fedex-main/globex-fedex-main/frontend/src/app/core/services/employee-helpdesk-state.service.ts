import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class EmployeeHelpdeskStateService {
  private readonly unreadSubject = new BehaviorSubject<number>(0);
  readonly unreadTickets$ = this.unreadSubject.asObservable();

  setUnread(count: number): void {
    this.unreadSubject.next(Math.max(0, count));
  }
}
