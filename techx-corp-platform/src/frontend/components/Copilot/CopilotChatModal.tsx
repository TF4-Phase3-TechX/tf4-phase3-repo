// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import React, { useState, useMemo } from 'react';
import CartActionCard, { CartActionProposalData } from './CartActionCard';

interface ChatMessage {
    id: string;
    sender: 'user' | 'assistant';
    text: string;
    proposal?: CartActionProposalData;
}

export const CopilotChatModal: React.FC = () => {
    const [isOpen, setIsOpen] = useState(false);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [messages, setMessages] = useState<ChatMessage[]>([]);

    const sessionId = useMemo(() => {
        if (typeof window !== 'undefined' && window.crypto?.randomUUID) {
            return window.crypto.randomUUID();
        }
        return `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    }, []);

    const handleSend = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || loading) return;

        const userMsgText = input.trim();
        const userMsg: ChatMessage = {
            id: `msg_${Date.now()}`,
            sender: 'user',
            text: userMsgText,
        };

        setMessages((prev) => [...prev, userMsg]);
        setInput('');
        setLoading(true);

        try {
            const response = await fetch('/api/product-search-ai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: userMsgText, sessionId }),
            });
            const data = await response.json();

            const assistantMsg: ChatMessage = {
                id: `msg_${Date.now() + 1}`,
                sender: 'assistant',
                text: data.response || 'Đã xử lý yêu cầu tìm kiếm.',
                proposal: data.actionProposal || data.action_proposal || undefined,
            };

            setMessages((prev) => [...prev, assistantMsg]);
        } catch (error) {
            setMessages((prev) => [
                ...prev,
                {
                    id: `msg_${Date.now() + 1}`,
                    sender: 'assistant',
                    text: 'Trợ lý AI hiện đang bận. Vui lòng thử lại sau.',
                },
            ]);
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) {
        return (
            <button
                onClick={() => setIsOpen(true)}
                className="fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3 text-sm font-semibold text-white bg-blue-600 rounded-full shadow-lg hover:bg-blue-700 transition-all transform hover:scale-105"
            >
                🤖 Shopping Copilot
            </button>
        );
    }

    return (
        <div className="fixed bottom-6 right-6 z-50 w-96 max-w-[calc(100vw-3rem)] h-[500px] bg-white rounded-2xl shadow-2xl border border-gray-200 flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 bg-blue-600 text-white font-semibold text-sm">
                <div className="flex items-center gap-2">
                    <span>🤖</span> Shopping Copilot (Multi-turn)
                </div>
                <button
                    onClick={() => setIsOpen(false)}
                    aria-label="Đóng cửa sổ chat Copilot"
                    className="text-white hover:text-gray-200 font-bold text-lg"
                >
                    ✕
                </button>
            </div>

            <div className="flex-1 p-4 overflow-y-auto space-y-3 bg-gray-50 text-xs">
                {messages.length === 0 && (
                    <div className="text-center text-gray-400 my-8">
                        👋 Xin chào! Tôi là Trợ lý Shopping Copilot.<br />Bạn cần tìm kiếm hay thêm sản phẩm nào vào giỏ hàng?
                    </div>
                )}
                {messages.map((msg) => (
                    <div
                        key={msg.id}
                        className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}
                    >
                        <div
                            className={`px-3 py-2 rounded-xl max-w-[85%] leading-relaxed ${
                                msg.sender === 'user'
                                    ? 'bg-blue-600 text-white rounded-br-none'
                                    : 'bg-white text-gray-800 border border-gray-200 shadow-sm rounded-bl-none'
                            }`}
                        >
                            {msg.text}
                        </div>
                        {msg.proposal && (
                            <div className="w-full mt-1">
                                <CartActionCard proposal={msg.proposal} />
                            </div>
                        )}
                    </div>
                ))}
                {loading && (
                    <div className="text-gray-400 italic text-xs">Copilot đang suy nghĩ...</div>
                )}
            </div>

            <form onSubmit={handleSend} className="p-3 bg-white border-t border-gray-200 flex gap-2">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Nhập câu hỏi hoặc yêu cầu mua sắm..."
                    className="flex-1 px-3 py-2 text-xs border border-gray-300 rounded-lg focus:outline-none focus:border-blue-500"
                />
                <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    className="px-3 py-2 text-xs font-semibold text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
                >
                    Gửi
                </button>
            </form>
        </div>
    );
};

export default CopilotChatModal;
