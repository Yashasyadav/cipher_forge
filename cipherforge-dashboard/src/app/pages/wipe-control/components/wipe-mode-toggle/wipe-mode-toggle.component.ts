import { Component, EventEmitter, Input, Output } from '@angular/core';
import { MatButtonToggleChange, MatButtonToggleModule } from '@angular/material/button-toggle';

import { WipeMode } from '../../../../core/models/api.models';

@Component({
  selector: 'app-wipe-mode-toggle',
  standalone: true,
  imports: [MatButtonToggleModule],
  templateUrl: './wipe-mode-toggle.component.html',
  styleUrl: './wipe-mode-toggle.component.scss'
})
export class WipeModeToggleComponent {
  @Input() mode: WipeMode = 'DEVICE_WIPE';
  @Input() disabled = false;
  @Output() readonly modeChange = new EventEmitter<WipeMode>();

  onModeChanged(event: MatButtonToggleChange): void {
    const nextMode = event.value as WipeMode;
    if (nextMode) {
      this.modeChange.emit(nextMode);
    }
  }
}
