import { CommonModule } from '@angular/common';
import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { TranslatePipe } from '../../../../core/i18n/translate.pipe';
import { AgentQuestion, AgentQuestionnaire } from '../../../../core/models/chat-send.model';

@Component({
  selector: 'app-agent-questionnaire',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslatePipe],
  templateUrl: './agent-questionnaire.component.html',
  styleUrl: './agent-questionnaire.component.scss',
})
export class AgentQuestionnaireComponent {
  @Input({ required: true }) questionnaire!: AgentQuestionnaire;
  @Input() disabled = false;

  @Output() submitAnswers = new EventEmitter<Record<string, string>>();

  readonly draft: Record<string, string> = {};

  onSelect(question: AgentQuestion, optionId: string): void {
    if (this.disabled) {
      return;
    }
    this.draft[question.id] = optionId;
  }

  onTextChange(question: AgentQuestion, value: string): void {
    this.draft[question.id] = value.trim();
  }

  isSelected(question: AgentQuestion, optionId: string): boolean {
    return this.draft[question.id] === optionId;
  }

  canSubmit(): boolean {
    if (this.disabled) {
      return false;
    }
    return this.questionnaire.questions.every((q) => {
      if (q.required === false) {
        return true;
      }
      const val = (this.draft[q.id] || '').trim();
      if (q.question_type === 'text') {
        return val.length >= 10;
      }
      return val.length > 0;
    });
  }

  submit(): void {
    if (!this.canSubmit()) {
      return;
    }
    this.submitAnswers.emit({ ...this.draft });
  }
}
