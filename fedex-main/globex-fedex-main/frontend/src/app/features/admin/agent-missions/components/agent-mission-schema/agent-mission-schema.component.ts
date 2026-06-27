import { CommonModule } from '@angular/common';
import { Component, Input } from '@angular/core';

import { MissionWorkflowSchema, AGENT_OPTIONS } from '../../../../../core/services/agent-missions.service';

@Component({
  selector: 'app-agent-mission-schema',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './agent-mission-schema.component.html',
  styleUrl: './agent-mission-schema.component.scss',
})
export class AgentMissionSchemaComponent {
  @Input({ required: true }) schema!: MissionWorkflowSchema | null;
  @Input() missionStatus: string | null = null;

  suggestedAgentLabel(): string {
    const suggested = this.schema?.decision?.suggested_agent;
    if (!suggested) return '';
    return AGENT_OPTIONS.find((a) => a.value === suggested)?.label || suggested;
  }
}
