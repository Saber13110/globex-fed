import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api.config';

export interface TrackingEvent {
  at: string;
  description: string;
  location: string;
  city?: string;
  state_or_province?: string;
  country?: string;
  event_type?: string;
  status_code?: string;
}

export interface VisibilityEvent {
  id?: number;
  tracking_number: string;
  event_type: string;
  event_type_label?: string;
  description: string;
  location?: string | null;
  occurred_at?: string | null;
  source?: string | null;
}

export interface PodInfo {
  tracking_number: string;
  status?: string | null;
  delivered_at?: string | null;
  delivery_address?: string | null;
  received_by_name?: string | null;
  signature_available?: boolean;
  carrier_service?: string | null;
}

export interface SpecialHandling {
  type: string;
  description: string;
  payment_type?: string;
}

export interface AvailableImage {
  type: string;
  size?: string;
}

export interface TrackingResponse {
  tracking_number: string;
  status: string | null;
  status_code?: string | null;
  status_description?: string | null;
  current_location: string | null;
  city?: string | null;
  state_or_province?: string | null;
  country?: string | null;
  estimated_delivery: string | null;
  actual_delivery?: string | null;
  events: TrackingEvent[];
  visibility_events?: VisibilityEvent[];
  service_type?: string | null;
  service_description?: string | null;
  shipper?: string | null;
  recipient?: string | null;
  origin_location?: string | null;
  destination_location?: string | null;
  weight: string | null;
  dimensions: string | null;
  package_type?: string | null;
  package_count?: string | null;
  special_handlings?: SpecialHandling[];
  delivery_details?: Record<string, unknown> | null;
  received_by_name?: string | null;
  available_images?: AvailableImage[];
  available_notifications?: string[];
  hold_at_location?: Record<string, unknown> | null;
  service_commit_message?: string | null;
  pod_available: boolean;
  pod_info?: PodInfo | null;
  source?: string | null;
  details: Record<string, unknown>;
}

export interface SandboxWhitelistErrorDetail {
  code: 'sandbox_whitelist_denied';
  message: string;
  tracking_number: string;
}

export function isSandboxWhitelistError(err: HttpErrorResponse): boolean {
  const detail = err?.error;
  return (
    typeof detail === 'object' &&
    detail !== null &&
    (detail as SandboxWhitelistErrorDetail).code === 'sandbox_whitelist_denied'
  );
}

export function sandboxWhitelistMessage(err: HttpErrorResponse): string {
  const detail = err?.error as SandboxWhitelistErrorDetail | undefined;
  return detail?.message || '';
}

@Injectable({ providedIn: 'root' })
export class TrackingService {
  constructor(private readonly http: HttpClient) {}

  getTracking(trackingNumber: string): Observable<TrackingResponse> {
    const encoded = encodeURIComponent(trackingNumber.trim());
    return this.http.get<TrackingResponse>(`${API_BASE_URL}/tracking/${encoded}`);
  }

  downloadProofOfDelivery(trackingNumber: string) {
    const encoded = encodeURIComponent(trackingNumber.trim());
    return this.http.get(`${API_BASE_URL}/tracking/${encoded}/proof-of-delivery`, {
      responseType: 'blob',
    });
  }
}
