import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// T3.5 — 5 modul HR AI → 1 hub
const RahazaAIModule = lazy(() => import('../RahazaAIModule'));
const HRAttritionModule = lazy(() => import('../hr/HRAttritionModule'));
const HRSkillGapModule = lazy(() => import('../hr/HRSkillGapModule'));
const HRCoachingModule = lazy(() => import('../hr/HRCoachingModule'));
const AIActionsModule = lazy(() => import('../AIActionsModule'));

export default function HRAIHub(props) {
  return (
    <HubTabs
      hubId="hr-ai-hub"
      tabs={[
        { key: 'insights', label: 'HR AI Insights', Component: RahazaAIModule },
        { key: 'attrition', label: 'Predictive Attrition', Component: HRAttritionModule },
        { key: 'skill-gap', label: 'Skill Gap', Component: HRSkillGapModule },
        { key: 'coaching', label: 'Coaching AI', Component: HRCoachingModule },
        { key: 'actions', label: 'Action Items', Component: AIActionsModule },
      ]}
      {...props}
    />
  );
}
