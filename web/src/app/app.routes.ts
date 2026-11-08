import { Routes } from '@angular/router';

import { AskComponent } from './ask/ask.component';
import { EvaluationComponent } from './evaluation/evaluation.component';
import { FilingsComponent } from './filings/filings.component';

export const routes: Routes = [
  { path: '', component: AskComponent, title: 'FilingLens · Ask' },
  { path: 'evaluation', component: EvaluationComponent, title: 'FilingLens · Evaluation' },
  { path: 'filings', component: FilingsComponent, title: 'FilingLens · Filings' },
  { path: '**', redirectTo: '' },
];
