// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import React, { useState, useMemo } from 'react';
import CartActionCard, { CartActionProposalData } from './CartActionCard';

interface ChatMessage {
    id: string;
    sender: 'user' | 'assistant';
    text: string;
    proposal?: CartActionProposalData;
    results?: any[];
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

            const proposal = data.actionProposal || data.action_proposal || undefined;
            const results = data.results || [];
            let assistantText = data.response;
            const traceObj = data.trace || {};
            const rawIntent = traceObj.parsedIntent || traceObj.parsed_intent;
            if (rawIntent) {
                try {
                    const parsed = typeof rawIntent === 'string' ? JSON.parse(rawIntent) : rawIntent;
                    if (parsed.response_message) {
                        assistantText = parsed.response_message;
                    } else if (parsed.search_type === 'clarify' && parsed.clarify_question) {
                        assistantText = parsed.clarify_question;
                    }
                } catch (e) {
                    // ignore
                }
            }

            if (!assistantText) {
                if (proposal) {
                    const prodName = proposal.productName || proposal.product_name || 'sản phẩm';
                    const qty = proposal.quantity || 1;
                    assistantText = `Tôi có thể giúp bạn thêm "${prodName}" (Số lượng: ${qty}) vào giỏ hàng. Vui lòng xác nhận bên dưới:`;
                } else if (Array.isArray(results) && results.length > 0) {
                    assistantText = `Dưới đây là các sản phẩm phù hợp với yêu cầu của bạn:`;
                } else {
                    const cleanQ = userMsgText.trim().toLowerCase();
                    const isGreeting = ['hi', 'hí', 'hello', 'chào', 'chào bạn', 'xin chào'].includes(cleanQ);
                    if (isGreeting) {
                        assistantText = `Xin chào! Tôi là Trợ lý Shopping Copilot. Tôi có thể giúp gì cho bạn hôm nay?`;
                    } else {
                        assistantText = `Rất tiếc, tôi chưa tìm thấy sản phẩm nào phù hợp với "${userMsgText}". Cửa hàng hiện có các sản phẩm như kính thiên văn, đèn pin, ống nhòm và sách thiên văn. Bạn thử tìm từ khóa khác xem sao nhé!`;
                    }
                }
            }

            const assistantMsg: ChatMessage = {
                id: `msg_${Date.now() + 1}`,
                sender: 'assistant',
                text: assistantText,
                proposal,
                results: Array.isArray(results) && results.length > 0 ? results : undefined,
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
                style={{
                    position: 'fixed',
                    bottom: '24px',
                    right: '24px',
                    zIndex: 99999,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '14px 22px',
                    fontSize: '14px',
                    fontWeight: 600,
                    color: '#ffffff',
                    backgroundColor: '#2563eb',
                    borderRadius: '50px',
                    boxShadow: '0 10px 25px -5px rgba(37, 99, 235, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.2)',
                    border: 'none',
                    cursor: 'pointer',
                    fontFamily: 'sans-serif',
                }}
            >
                🤖 Shopping Copilot
            </button>
        );
    }

    return (
        <div
            style={{
                position: 'fixed',
                bottom: '24px',
                right: '24px',
                zIndex: 99999,
                width: '380px',
                maxWidth: 'calc(100vw - 32px)',
                height: '520px',
                backgroundColor: '#ffffff',
                borderRadius: '16px',
                boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.3), 0 8px 10px -6px rgba(0, 0, 0, 0.2)',
                border: '1px solid #e5e7eb',
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
                fontFamily: 'sans-serif',
            }}
        >
            <div
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '12px 16px',
                    backgroundColor: '#2563eb',
                    color: '#ffffff',
                    fontWeight: 600,
                    fontSize: '14px',
                }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <span>🤖</span> Shopping Copilot
                </div>
                <button
                    onClick={() => setIsOpen(false)}
                    aria-label="Close Copilot"
                    style={{
                        background: 'none',
                        border: 'none',
                        color: '#ffffff',
                        fontSize: '18px',
                        cursor: 'pointer',
                        fontWeight: 'bold',
                    }}
                >
                    ✕
                </button>
            </div>

            <div
                style={{
                    flex: 1,
                    padding: '16px',
                    overflowY: 'auto',
                    backgroundColor: '#f9fafb',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                    fontSize: '13px',
                }}
            >
                {messages.length === 0 && (
                    <div style={{ textAlign: 'center', color: '#9ca3af', margin: '32px 0' }}>
                        👋 Xin chào! Tôi là Trợ lý Shopping Copilot.<br />Bạn cần tìm kiếm hay thêm sản phẩm nào vào giỏ hàng?
                    </div>
                )}
                {messages.map((msg) => (
                    <div
                        key={msg.id}
                        style={{
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                        }}
                    >
                        <div
                            style={{
                                padding: '10px 14px',
                                borderRadius: '12px',
                                maxWidth: '85%',
                                lineHeight: '1.4',
                                backgroundColor: msg.sender === 'user' ? '#2563eb' : '#ffffff',
                                color: msg.sender === 'user' ? '#ffffff' : '#1f2937',
                                border: msg.sender === 'user' ? 'none' : '1px solid #e5e7eb',
                                boxShadow: msg.sender === 'user' ? 'none' : '0 1px 2px rgba(0,0,0,0.05)',
                                whiteSpace: 'pre-line',
                            }}
                        >
                            {msg.text}
                        </div>
                        {msg.proposal && (
                            <div style={{ width: '100%', marginTop: '4px' }}>
                                <CartActionCard proposal={msg.proposal} />
                            </div>
                        )}
                        {msg.results && msg.results.length > 0 && (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '6px', width: '100%', maxWidth: '90%' }}>
                                {msg.results.map((p: any) => {
                                    const priceVal = p.priceUsd ? (p.priceUsd.units || 0) + (p.priceUsd.nanos || 0) / 1e9 : 0;
                                    const priceStr = priceVal > 0 ? `$${priceVal.toFixed(2)}` : '';
                                    return (
                                        <a
                                            key={p.id}
                                            href={`/product/${p.id}`}
                                            style={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: '10px',
                                                padding: '10px',
                                                backgroundColor: '#ffffff',
                                                border: '1px solid #e5e7eb',
                                                borderRadius: '10px',
                                                textDecoration: 'none',
                                                color: 'inherit',
                                                boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                                                cursor: 'pointer',
                                            }}
                                        >
                                            {p.picture && (
                                                <img
                                                    src={`/images/products/${p.picture}`}
                                                    alt={p.name}
                                                    style={{
                                                        width: '50px',
                                                        height: '50px',
                                                        objectFit: 'contain',
                                                        borderRadius: '6px',
                                                        backgroundColor: '#f9fafb',
                                                        flexShrink: 0,
                                                    }}
                                                />
                                            )}
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{ fontWeight: 600, fontSize: '13px', color: '#111827', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                                    {p.name}
                                                </div>
                                                {p.description && (
                                                    <div style={{ fontSize: '11px', color: '#6b7280', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', marginTop: '2px' }}>
                                                        {p.description}
                                                    </div>
                                                )}
                                                {priceStr && (
                                                    <div style={{ fontWeight: 700, fontSize: '12px', color: '#2563eb', marginTop: '3px' }}>
                                                        {priceStr}
                                                    </div>
                                                )}
                                            </div>
                                        </a>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                ))}
                {loading && (
                    <div style={{ color: '#9ca3af', fontStyle: 'italic', fontSize: '12px' }}>
                        Copilot đang suy nghĩ...
                    </div>
                )}
            </div>

            <form
                onSubmit={handleSend}
                style={{
                    padding: '12px',
                    backgroundColor: '#ffffff',
                    borderTop: '1px solid #e5e7eb',
                    display: 'flex',
                    gap: '8px',
                }}
            >
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Nhập câu hỏi hoặc yêu cầu..."
                    style={{
                        flex: 1,
                        padding: '8px 12px',
                        fontSize: '13px',
                        border: '1px solid #d1d5db',
                        borderRadius: '8px',
                        outline: 'none',
                    }}
                />
                <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    style={{
                        padding: '8px 14px',
                        fontSize: '13px',
                        fontWeight: 600,
                        color: '#ffffff',
                        backgroundColor: loading || !input.trim() ? '#93c5fd' : '#2563eb',
                        border: 'none',
                        borderRadius: '8px',
                        cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                    }}
                >
                    Gửi
                </button>
            </form>
        </div>
    );
};

export default CopilotChatModal;
