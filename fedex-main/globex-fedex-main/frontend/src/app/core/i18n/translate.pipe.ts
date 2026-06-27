import { Pipe, PipeTransform } from '@angular/core';

import { I18nService } from './i18n.service';

@Pipe({
  name: 't',
  standalone: true,
  pure: false,
})
export class TranslatePipe implements PipeTransform {
  constructor(private readonly i18n: I18nService) {}

  transform(key: string, params?: Record<string, string>): string {
    this.i18n.lang();
    return this.i18n.t(key, params);
  }
}
