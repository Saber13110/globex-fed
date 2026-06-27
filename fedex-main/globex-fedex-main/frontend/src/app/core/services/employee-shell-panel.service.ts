import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

export type EmployeeSettingsTab = 'profile' | 'security' | 'appearance' | 'language';

@Injectable({ providedIn: 'root' })
export class EmployeeShellPanelService {
  private readonly openSettings$ = new Subject<EmployeeSettingsTab>();
  private readonly openHelp$ = new Subject<void>();

  requestSettings(tab: EmployeeSettingsTab = 'profile'): void {
    this.openSettings$.next(tab);
  }

  requestHelp(): void {
    this.openHelp$.next();
  }

  onOpenSettings() {
    return this.openSettings$.asObservable();
  }

  onOpenHelp() {
    return this.openHelp$.asObservable();
  }
}
