// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import React, { useState } from 'react';
import { useCart } from '../../providers/Cart.provider';

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
    onConfirmed?: () => void;
    onCancelled?: () => void;
}

export const CartActionCard: React.FC<CartActionCardProps> = ({ proposal, onConfirmed, onCancelled }) => {
    const { addItem } = useCart();
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [isConfirmed, setIsConfirmed] = useState(false);
    const [isCancelled, setIsCancelled] = useState(false);

    const handleConfirm = async () => {
        if (isSubmitting || isConfirmed || isCancelled) return;
        setIsSubmitting(true);
        try {
            await addItem({
                productId: proposal.productId,
                quantity: proposal.quantity || 1,
            });
            setIsConfirmed(true);
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
            <div className="p-3 my-2 text-sm text-gray-500 bg-gray-100 rounded-lg border border-gray-200">
                🚫 Đã hủy gợi ý thêm vào giỏ hàng.
            </div>
        );
    }

    if (isConfirmed) {
        return (
            <div className="p-3 my-2 text-sm text-green-700 bg-green-50 rounded-lg border border-green-200">
                ✅ Đã thêm {proposal.quantity || 1} x <strong>{proposal.productName}</strong> vào giỏ hàng thành công!
            </div>
        );
    }

    return (
        <div className="p-4 my-2 text-sm bg-white rounded-xl border border-blue-200 shadow-sm">
            <div className="flex items-center gap-2 mb-2 text-blue-700 font-semibold">
                🛒 Gợi ý hành động mua sắm
            </div>
            <div className="mb-3 text-gray-700">
                Bạn có muốn thêm <strong>{proposal.productName}</strong> (Số lượng: {proposal.quantity || 1}) vào giỏ hàng không?
            </div>
            <div className="flex gap-2">
                <button
                    onClick={handleConfirm}
                    disabled={isSubmitting}
                    className="px-4 py-2 text-xs font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                    {isSubmitting ? 'Đang xử lý...' : 'Thêm vào giỏ hàng'}
                </button>
                <button
                    onClick={handleCancel}
                    disabled={isSubmitting}
                    aria-label="Hủy thao tác thêm vào giỏ hàng"
                    className="px-4 py-2 text-xs font-semibold text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50 transition-colors"
                >
                    Hủy
                </button>
            </div>
        </div>
    );
};

export default CartActionCard;
