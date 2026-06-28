import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '../../core/services/auth.service';
import { TranslatePipe } from '../../core/i18n/translate.pipe';

@Component({
  selector: 'app-employee-portal',
  standalone: true,
  imports: [CommonModule, RouterLink, TranslatePipe],
  templateUrl: './employee-portal.component.html',
  styleUrl: './employee-portal.component.scss',
})
export class EmployeePortalComponent implements OnInit {
  accountName = '';

  constructor(
    private readonly auth: AuthService,
    private readonly router: Router,
  ) {}

  ngOnInit(): void {
    if (!this.auth.token()) {
      void this.router.navigateByUrl('/employee/login');
      return;
    }
    this.auth.me().subscribe({
      next: (p) => {
        this.accountName = p.full_name;
      },
    });
  }
}
