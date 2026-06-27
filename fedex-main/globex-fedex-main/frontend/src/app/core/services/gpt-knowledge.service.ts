import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api.config';

export interface GptKnowledgeProfile {
  slug: string;
  name: string;
  collections: number;
  chunks: number;
  embedded_chunks: number;
  documents: number;
}

export interface KnowledgeCollectionRow {
  id: number;
  slug: string;
  title: string;
  language: string;
  source_type: string;
  chunk_count: number;
  document_count: number;
}

export interface KnowledgeDocumentRow {
  id: number;
  collection_id: number;
  original_filename: string;
  file_size_bytes: number;
  status: string;
  chunk_count: number;
  error_message?: string | null;
  created_at?: string | null;
}

@Injectable({ providedIn: 'root' })
export class GptKnowledgeService {
  constructor(private readonly http: HttpClient) {}

  getOverview(): Observable<{ gpt_profiles: GptKnowledgeProfile[] }> {
    return this.http.get<{ gpt_profiles: GptKnowledgeProfile[] }>(
      `${API_BASE_URL}/admin/gpt/knowledge/overview`,
    );
  }

  getDocuments(gptSlug: string): Observable<KnowledgeDocumentRow[]> {
    return this.http.get<KnowledgeDocumentRow[]>(`${API_BASE_URL}/admin/gpt/knowledge/documents`, {
      params: { gpt_slug: gptSlug },
    });
  }

  upload(file: File, gptSlug: string, language: string): Observable<{ document_id: number; chunk_count: number; status: string; filename: string }> {
    const form = new FormData();
    form.append('file', file, file.name);
    form.append('gpt_slug', gptSlug);
    form.append('language', language);
    return this.http.post<{ document_id: number; chunk_count: number; status: string; filename: string }>(
      `${API_BASE_URL}/admin/gpt/knowledge/upload`,
      form,
    );
  }

  reindex(gptSlug?: string): Observable<{ reindexed: number }> {
    return this.http.post<{ reindexed: number }>(`${API_BASE_URL}/admin/gpt/knowledge/reindex`, null, {
      params: gptSlug ? { gpt_slug: gptSlug } : {},
    });
  }

  deleteDocument(id: number): Observable<void> {
    return this.http.delete<void>(`${API_BASE_URL}/admin/gpt/knowledge/documents/${id}`);
  }
}
