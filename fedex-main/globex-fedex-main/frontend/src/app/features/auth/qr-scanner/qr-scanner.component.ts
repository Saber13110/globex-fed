import { CommonModule } from '@angular/common';
import {
  AfterViewInit,
  Component,
  ElementRef,
  EventEmitter,
  OnDestroy,
  Output,
  ViewChild,
} from '@angular/core';
import { Html5Qrcode, Html5QrcodeCameraScanConfig } from 'html5-qrcode';

import { I18nService } from '../../../core/i18n/i18n.service';
import { TranslatePipe } from '../../../core/i18n/translate.pipe';

interface CameraOption {
  id: string;
  label: string;
}

@Component({
  selector: 'app-qr-scanner',
  standalone: true,
  imports: [CommonModule, TranslatePipe],
  templateUrl: './qr-scanner.component.html',
  styleUrl: './qr-scanner.component.scss',
})
export class QrScannerComponent implements AfterViewInit, OnDestroy {
  @Output() scanned = new EventEmitter<string>();
  @Output() closed = new EventEmitter<void>();

  @ViewChild('readerHost') readerHost?: ElementRef<HTMLElement>;

  error: string | null = null;
  starting = true;
  cameras: CameraOption[] = [];
  selectedCameraId = '';
  mode: 'camera' | 'file' = 'camera';

  readonly elementId = `globex-qr-${Math.random().toString(36).slice(2, 10)}`;

  private scanner: Html5Qrcode | null = null;
  private destroyed = false;

  constructor(private readonly i18n: I18nService) {}

  private readonly scanConfig: Html5QrcodeCameraScanConfig = {
    fps: 10,
    qrbox: (viewfinderWidth, viewfinderHeight) => {
      const edge = Math.min(viewfinderWidth, viewfinderHeight);
      const size = Math.max(180, Math.floor(edge * 0.75));
      return { width: size, height: size };
    },
  };

  ngAfterViewInit(): void {
    // Attendre que le conteneur vidéo soit bien dans le DOM.
    requestAnimationFrame(() => {
      if (!this.destroyed) {
        void this.initScanner();
      }
    });
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    void this.stopScanner();
  }

  close(): void {
    void this.stopScanner();
    this.closed.emit();
  }

  async retryCamera(): Promise<void> {
    this.error = null;
    this.starting = true;
    this.mode = 'camera';
    await this.stopScanner();
    void this.initScanner();
  }

  async onCameraChange(cameraId: string): Promise<void> {
    if (!cameraId || cameraId === this.selectedCameraId) {
      return;
    }
    this.selectedCameraId = cameraId;
    this.error = null;
    this.starting = true;
    await this.stopScanner();
    await this.startWithCamera(cameraId);
  }

  async onImageSelected(event: Event): Promise<void> {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) {
      return;
    }

    this.mode = 'file';
    this.error = null;
    this.starting = true;
    await this.stopScanner();

    try {
      const scanner = new Html5Qrcode(this.elementId);
      const decoded = await scanner.scanFile(file, false);
      scanner.clear();
      this.starting = false;
      this.scanned.emit(decoded);
    } catch {
      this.starting = false;
      this.error = this.i18n.t('auth.qr.noQrInImage');
      this.mode = 'camera';
      void this.initScanner();
    }
  }

  private async initScanner(): Promise<void> {
    if (!document.getElementById(this.elementId)) {
      this.starting = false;
      this.error = this.i18n.t('auth.qr.displayError');
      return;
    }

    this.scanner = new Html5Qrcode(this.elementId, /* verbose= */ false);

    try {
      let devices = await Html5Qrcode.getCameras();

      // Sur Windows, la liste est parfois vide avant la première autorisation caméra.
      if (!devices.length) {
        const granted = await this.startWithFacingMode('user');
        if (granted) {
          return;
        }
        devices = await Html5Qrcode.getCameras();
      }

      if (!devices.length) {
        this.starting = false;
        this.error = this.i18n.t('auth.qr.noWebcam');
        return;
      }

      this.cameras = devices.map((d) => ({
        id: d.id,
        label: d.label?.trim() || `Caméra ${d.id.slice(0, 8)}…`,
      }));
      this.selectedCameraId = this.pickDefaultWebcam(this.cameras).id;
      await this.startWithCamera(this.selectedCameraId);
    } catch (err) {
      const granted = await this.startWithFacingMode('user');
      if (!granted) {
        this.starting = false;
        this.error = this.formatError(err, this.i18n.t('auth.qr.cameraDenied'));
      }
    }
  }

  private pickDefaultWebcam(list: CameraOption[]): CameraOption {
    const preferred = list.find((c) =>
      /webcam|integrated|facetime|usb|hd|front|user|built|camera/i.test(c.label),
    );
    return preferred ?? list[0];
  }

  private async startWithCamera(cameraId: string): Promise<void> {
    if (!this.scanner) {
      this.scanner = new Html5Qrcode(this.elementId, false);
    }
    try {
      await this.scanner.start(
        cameraId,
        this.scanConfig,
        (decoded) => {
          this.scanned.emit(decoded);
          void this.stopScanner();
        },
        () => undefined,
      );
      this.starting = false;
      this.error = null;
    } catch (err) {
      this.starting = false;
      this.error = this.formatError(err, this.i18n.t('auth.qr.cameraOpenFailed'));
    }
  }

  private async startWithFacingMode(mode: 'user' | 'environment'): Promise<boolean> {
    if (!this.scanner) {
      this.scanner = new Html5Qrcode(this.elementId, false);
    }
    try {
      await this.scanner.start(
        { facingMode: mode },
        this.scanConfig,
        (decoded) => {
          this.scanned.emit(decoded);
          void this.stopScanner();
        },
        () => undefined,
      );
      this.starting = false;
      this.error = null;
      return true;
    } catch (err) {
      if (mode === 'user') {
        return this.startWithFacingMode('environment');
      }
      this.starting = false;
      this.error = this.formatError(err, this.i18n.t('auth.qr.accessDenied'));
      return false;
    }
  }

  private formatError(err: unknown, fallback: string): string {
    if (err instanceof Error && err.message) {
      return `${fallback} (${err.message})`;
    }
    return fallback;
  }

  private async stopScanner(): Promise<void> {
    if (this.scanner?.isScanning) {
      try {
        await this.scanner.stop();
      } catch {
        /* ignore */
      }
    }
    try {
      this.scanner?.clear();
    } catch {
      /* ignore */
    }
    this.scanner = null;
  }
}
