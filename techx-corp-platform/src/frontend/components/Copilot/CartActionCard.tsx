// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import React, { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

export interface CartActionProposalData {
    actionType: string;
    productId: string;
    productName: string;
    quantity: number;
    confirmationRequired: boolean;
    idempotencyKey: string;
}

interface CartActionCardProps {
    proposal: CartActionProposalData;
    userId: string;
    sessionId: string;
    onConfirmed?: () => void;
    onCancelled?: () => void;
}

export const CartActionCard: React.FC<CartActionCardProps> = ({ proposal, userId, sessionId, onConfirmed, onCancelled }) => {
    const queryClient = useQueryClient();
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [isConfirmed, setIsConfirmed] = useState(false);
    const [isCancelled, setIsCancelled] = useState(false);
    const [hasError, setHasError] = useState(false);

    const handleConfirm = async () => {
        if (isSubmitting || isConfirmed || isCancelled || hasError) return;
        setIsSubmitting(true);
        try {
            const response = await fetch('/api/copilot-cart-confirm', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    userId,
                    sessionId,
                    confirmationToken: proposal.idempotencyKey,
                }),
            });
            if (!response.ok) throw new Error('Proposal is invalid, expired, or already used');
            setIsConfirmed(true);
            await queryClient.invalidateQueries({ queryKey: ['cart'] });
            if (onConfirmed) onConfirmed();
        } catch (error) {
            console.error('Failed to add item to cart via Copilot proposal:', error);
            setHasError(true);
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleCancel = () => {
        setIsCancelled(true);
        if (onCancelled) onCancelled();
    };

    if (hasError) {
        return (
            <div style={{
                padding: '12px 16px',
                margin: '8px 0',
                fontSize: '13px',
                color: '#b91c1c',
                backgroundColor: '#fef2f2',
                borderRadius: '10px',
                border: '1px solid #fca5a5',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
            }}>
                <span style={{ fontSize: '16px' }}>⚠️</span>
                <span>Yêu cầu đã hết hạn hoặc đã được sử dụng. Vui lòng nhắn lại yêu cầu để tạo gợi ý mới!</span>
            </div>
        );
    }

    if (isCancelled) {
        return (
            <div style={{ 
                padding: '12px 16px', 
                margin: '8px 0', 
                fontSize: '13px', 
                color: '#6b7280', 
                backgroundColor: '#f9fafb', 
                borderRadius: '10px', 
                border: '1px solid #e5e7eb',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
            }}>
                <span style={{ fontSize: '16px' }}>🚫</span>
                <span>Đã hủy gợi ý thêm vào giỏ hàng.</span>
            </div>
        );
    }

    if (isConfirmed) {
        return (
            <div style={{ 
                padding: '12px 16px', 
                margin: '8px 0', 
                fontSize: '13px', 
                color: '#15803d', 
                backgroundColor: '#f0fdf4', 
                borderRadius: '10px', 
                border: '1px solid #86efac',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
            }}>
                <span style={{ fontSize: '16px' }}>✅</span>
                <span>
                    Đã thêm <strong>{proposal.quantity || 1} x {proposal.productName}</strong> vào giỏ hàng thành công!
                </span>
            </div>
        );
    }

    return (
        <div style={{ 
            padding: '16px', 
            margin: '8px 0', 
            fontSize: '13px', 
            backgroundColor: '#fef3c7', 
            borderRadius: '12px', 
            border: '2px solid #fbbf24',
            boxShadow: '0 2px 6px rgba(251, 191, 36, 0.15)'
        }}>
            <div style={{ 
                display: 'flex', 
                alignItems: 'center', 
                gap: '8px', 
                marginBottom: '10px', 
                color: '#92400e', 
                fontWeight: 700,
                fontSize: '14px'
            }}>
                🛒 Xác nhận thêm vào giỏ hàng
            </div>
            <div style={{ 
                marginBottom: '14px', 
                color: '#78350f',
                lineHeight: '1.5'
            }}>
                <div style={{ fontWeight: 600, marginBottom: '4px' }}>
                    Sản phẩm: <span style={{ color: '#92400e' }}>{proposal.productName}</span>
                </div>
                <div>
                    Số lượng: <span style={{ fontWeight: 600, color: '#92400e' }}>{proposal.quantity || 1}</span>
                </div>
            </div>
            <div style={{ display: 'flex', gap: '10px' }}>
                <button
                    onClick={handleConfirm}
                    disabled={isSubmitting}
                    style={{
                        padding: '10px 18px',
                        fontSize: '13px',
                        fontWeight: 600,
                        color: '#ffffff',
                        backgroundColor: isSubmitting ? '#93c5fd' : '#2563eb',
                        border: 'none',
                        borderRadius: '8px',
                        cursor: isSubmitting ? 'not-allowed' : 'pointer',
                        boxShadow: isSubmitting ? 'none' : '0 2px 4px rgba(37, 99, 235, 0.3)',
                        transition: 'all 0.2s',
                    }}
                    onMouseEnter={(e) => {
                        if (!isSubmitting) {
                            e.currentTarget.style.backgroundColor = '#1d4ed8';
                            e.currentTarget.style.transform = 'translateY(-1px)';
                        }
                    }}
                    onMouseLeave={(e) => {
                        if (!isSubmitting) {
                            e.currentTarget.style.backgroundColor = '#2563eb';
                            e.currentTarget.style.transform = 'translateY(0)';
                        }
                    }}
                >
                    {isSubmitting ? '⏳ Đang thêm...' : '✓ Xác nhận'}
                </button>
                <button
                    onClick={handleCancel}
                    disabled={isSubmitting}
                    style={{
                        padding: '10px 18px',
                        fontSize: '13px',
                        fontWeight: 600,
                        color: '#4b5563',
                        backgroundColor: '#f3f4f6',
                        border: '1px solid #d1d5db',
                        borderRadius: '8px',
                        cursor: isSubmitting ? 'not-allowed' : 'pointer',
                        transition: 'all 0.2s',
                    }}
                    onMouseEnter={(e) => {
                        if (!isSubmitting) {
                            e.currentTarget.style.backgroundColor = '#e5e7eb';
                        }
                    }}
                    onMouseLeave={(e) => {
                        if (!isSubmitting) {
                            e.currentTarget.style.backgroundColor = '#f3f4f6';
                        }
                    }}
                >
                    ✕ Hủy
                </button>
            </div>
        </div>
    );
};

export default CartActionCard;
