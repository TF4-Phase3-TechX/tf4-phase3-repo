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

    const handleConfirm = async () => {
        if (isSubmitting || isConfirmed || isCancelled) return;
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
        } finally {
            setIsSubmitting(false);
        }
    };

    const handleCancel = () => {
        setIsCancelled(true);
        if (onCancelled) onCancelled();
    };

    if (isCancelled) {
        return (
            <div style={{ padding: '12px', margin: '8px 0', fontSize: '13px', color: '#6b7280', backgroundColor: '#f3f4f6', borderRadius: '8px', border: '1px solid #e5e7eb' }}>
                🚫 Đã hủy gợi ý thêm vào giỏ hàng.
            </div>
        );
    }

    if (isConfirmed) {
        return (
            <div style={{ padding: '12px', margin: '8px 0', fontSize: '13px', color: '#15803d', backgroundColor: '#f0fdf4', borderRadius: '8px', border: '1px solid #bbf7d0' }}>
                ✅ Đã thêm {proposal.quantity || 1} x <strong>{proposal.productName}</strong> vào giỏ hàng thành công!
            </div>
        );
    }

    return (
        <div style={{ padding: '14px', margin: '8px 0', fontSize: '13px', backgroundColor: '#ffffff', borderRadius: '12px', border: '1px solid #bfdbfe', boxShadow: '0 2px 4px rgba(0,0,0,0.05)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px', color: '#1d4ed8', fontWeight: 600 }}>
                🛒 Gợi ý hành động mua sắm
            </div>
            <div style={{ marginBottom: '12px', color: '#374151' }}>
                Bạn có muốn thêm <strong>{proposal.productName}</strong> (Số lượng: {proposal.quantity || 1}) vào giỏ hàng không?
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
                <button
                    onClick={handleConfirm}
                    disabled={isSubmitting}
                    style={{
                        padding: '8px 14px',
                        fontSize: '12px',
                        fontWeight: 600,
                        color: '#ffffff',
                        backgroundColor: isSubmitting ? '#93c5fd' : '#2563eb',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: isSubmitting ? 'not-allowed' : 'pointer',
                    }}
                >
                    {isSubmitting ? 'Đang xử lý...' : 'Thêm vào giỏ hàng'}
                </button>
                <button
                    onClick={handleCancel}
                    disabled={isSubmitting}
                    style={{
                        padding: '8px 14px',
                        fontSize: '12px',
                        fontWeight: 600,
                        color: '#4b5563',
                        backgroundColor: '#f3f4f6',
                        border: '1px solid #d1d5db',
                        borderRadius: '6px',
                        cursor: 'pointer',
                    }}
                >
                    Hủy
                </button>
            </div>
        </div>
    );
};

export default CartActionCard;
