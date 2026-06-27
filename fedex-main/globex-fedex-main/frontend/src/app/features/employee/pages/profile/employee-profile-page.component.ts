import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';

@Component({
  selector: 'app-employee-profile-page',
  standalone: true,
  template: '',
})
export class EmployeeProfilePageComponent implements OnInit {
  constructor(private readonly router: Router) {}

  ngOnInit(): void {
    void this.router.navigate(['/employee/settings'], { replaceUrl: true });
  }
}
