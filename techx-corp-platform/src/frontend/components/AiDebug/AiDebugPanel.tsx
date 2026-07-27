// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import React from 'react';
import type { AiDebugMetadata } from '../../utils/aiDebugMetadata';

interface AiDebugPanelProps {
  metadata?: AiDebugMetadata;
}

const displayCost = (value: number) => (
  value > 0 ? `$${value.toFixed(6)}` : '$0'
);

const AiDebugPanel = ({ metadata }: AiDebugPanelProps) => {
  if (!metadata) return null;

  const isHit = metadata.cacheStatus === 'hit';
  const items = [
    ['Reason', metadata.cacheReason || '—'],
    ['Eligible', metadata.cacheEligible ? 'yes' : 'no'],
    ['Latency', `${metadata.latencyMs.toFixed(1)} ms`],
    ['Model calls', String(metadata.modelCalls)],
    ['Tokens', `${metadata.inputTokens} in / ${metadata.outputTokens} out`],
    ['Cost', displayCost(metadata.estimatedCostUsd)],
  ];
  if (metadata.memoryStatus && metadata.memoryStatus !== 'not_applicable') {
    items.push(['Memory', metadata.memoryStatus]);
  }

  return (
    <details
      data-cy="AiDebugMetadata"
      style={{
        marginTop: '8px',
        maxWidth: '100%',
        border: '1px dashed #a5b4fc',
        borderRadius: '8px',
        background: '#f5f7ff',
        color: '#374151',
        fontSize: '11px',
      }}
    >
      <summary
        style={{
          padding: '7px 9px',
          cursor: 'pointer',
          fontWeight: 700,
          listStylePosition: 'inside',
        }}
      >
        AI diagnostics{' '}
        <span
          style={{
            marginLeft: '4px',
            padding: '2px 6px',
            borderRadius: '999px',
            color: isHit ? '#166534' : '#92400e',
            background: isHit ? '#dcfce7' : '#fef3c7',
          }}
        >
          {metadata.cacheStatus.toUpperCase()}
        </span>
      </summary>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'max-content minmax(0, 1fr)',
          gap: '4px 10px',
          padding: '0 10px 9px',
        }}
      >
        {items.map(([label, value]) => (
          <React.Fragment key={label}>
            <span style={{ color: '#6b7280' }}>{label}</span>
            <span style={{ fontFamily: 'monospace', overflowWrap: 'anywhere' }}>
              {value}
            </span>
          </React.Fragment>
        ))}
      </div>
    </details>
  );
};

export default AiDebugPanel;
