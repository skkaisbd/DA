import React, { lazy } from 'react';
import HubTabs from './HubTabs';

// T3.4 — 4 modul Marketing AI → 1 hub
const MarketingAIInsightsDashboard = lazy(() => import('../marketing/MarketingAIInsightsDashboard'));
const AdvancedAIModule = lazy(() => import('../marketing/AdvancedAIModule'));
const AIContentGeneratorModule = lazy(() => import('../marketing/AIContentGeneratorModule'));
const AIImageGeneratorModule = lazy(() => import('../marketing/AIImageGeneratorModule'));

export default function MarketingAIHub(props) {
  return (
    <HubTabs
      hubId="marketing-ai-hub"
      tabs={[
        { key: 'insights', label: 'AI Insights', Component: MarketingAIInsightsDashboard },
        { key: 'advanced', label: 'Advanced AI', Component: AdvancedAIModule },
        { key: 'content', label: 'Content Generator', Component: AIContentGeneratorModule },
        { key: 'image', label: 'Image Generator', Component: AIImageGeneratorModule },
      ]}
      {...props}
    />
  );
}
