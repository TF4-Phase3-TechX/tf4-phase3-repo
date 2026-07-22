// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import React, { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import CartActionCard, { CartActionProposalData } from './CartActionCard';

interface ChatMessage {
    id: string;
    sender: 'user' | 'assistant';
    text: string;
    proposal?: CartActionProposalData;
    results?: any[];
    isQuickAction?: boolean;
}

// Removed CopilotMode - chatbot now understands intent naturally

const WELCOME_MESSAGE: ChatMessage = {
    id: 'welcome',
    sender: 'assistant',
    text: '👋 Xin chào! Tôi là trợ lý mua sắm thông minh của bạn.\n\nBạn có thể nói với tôi những gì bạn cần, ví dụ:\n• "Tìm kính thiên văn giá rẻ"\n• "Đánh giá sản phẩm Eclipsmart thế nào?"\n• "Thêm sách The Comet Book vào giỏ hàng"\n\nChỉ cần chat với tôi tự nhiên, tôi sẽ hiểu ý bạn!',
};

export const CopilotChatModal: React.FC = () => {
    const [isOpen, setIsOpen] = useState(false);
    const [input, setInput] = useState('');
    const [loading, setLoading] = useState(false);
    const [messages, setMessages] = useState<ChatMessage[]>([WELCOME_MESSAGE]);
    // Removed activeMode and showQuickActions - chatbot understands intent naturally
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const [fabHovered, setFabHovered] = useState(false);
    const [lastProductId, setLastProductId] = useState<string>('');

    const sessionId = useMemo(() => {
        if (typeof window !== 'undefined' && window.crypto?.randomUUID) {
            return window.crypto.randomUUID();
        }
        return `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    }, []);

    const scrollToBottom = useCallback(() => {
        setTimeout(() => {
            messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }, 100);
    }, []);

    useEffect(() => {
        scrollToBottom();
    }, [messages, loading, scrollToBottom]);

    // Auto-resize textarea
    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 100) + 'px';
        }
    }, [input]);

    // Remove quick action handler - chatbot now handles all intents naturally

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

        const isReviewQuery = ['review', 'đánh giá', 'nhận xét', 'chất lượng', 'dùng tốt không', 'tốt không'].some(kw => userMsgText.toLowerCase().includes(kw));

        try {
            if (isReviewQuery && lastProductId) {
                const askRes = await fetch(`/api/product-ask-ai-assistant/${lastProductId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ question: userMsgText, sessionId }),
                });
                const askData = await askRes.json();
                const reviewAnswerText = askData.response || `Dưới đây là thông tin về sản phẩm bạn đang quan tâm.`;

                const assistantMsg: ChatMessage = {
                    id: `msg_${Date.now() + 1}`,
                    sender: 'assistant',
                    text: reviewAnswerText,
                    proposal: askData.action_proposal || askData.actionProposal,
                };
                setMessages((prev) => [...prev, assistantMsg]);
                setLoading(false);
                return;
            }

            const response = await fetch('/api/product-search-ai', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query: userMsgText, sessionId }),
            });
            const data = await response.json();

            const proposal = data.actionProposal || data.action_proposal || undefined;
            const results = data.results || [];
            if (Array.isArray(results) && results.length > 0 && results[0]?.id) {
                setLastProductId(results[0].id);
            }
            let assistantText = data.response;
            const traceObj = data.trace || {};
            const rawIntent = traceObj.parsedIntent || traceObj.parsed_intent;
            let parsedType = '';
            if (rawIntent) {
                try {
                    const parsed = typeof rawIntent === 'string' ? JSON.parse(rawIntent) : rawIntent;
                    parsedType = parsed.search_type || '';
                    if (parsedType !== 'reviews' && parsed.response_message) {
                        assistantText = parsed.response_message;
                    } else if ((parsed.search_type === 'clarify' || parsed.search_type === 'unclear') && parsed.clarify_question) {
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
                } else if (Array.isArray(results) && results.length > 0 && parsedType !== 'reviews') {
                    assistantText = `Dưới đây là các sản phẩm phù hợp với yêu cầu của bạn:`;
                } else {
                    const cleanQ = userMsgText.trim().toLowerCase();
                    const isGreeting = ['hi', 'hí', 'hello', 'chào', 'chào bạn', 'xin chào'].includes(cleanQ);
                    if (isGreeting) {
                        assistantText = `Xin chào! Tôi là Trợ lý Shopping Copilot. Tôi có thể giúp gì cho bạn hôm nay?`;
                    } else {
                        assistantText = `Rất tiếc, tôi chưa tìm thấy thông tin phù hợp với "${userMsgText}". Cửa hàng hiện có các sản phẩm như kính thiên văn, đèn pin, ống nhòm và sách thiên văn. Bạn thử tìm từ khóa khác xem sao nhé!`;
                    }
                }
            }

            const shouldShowResults = parsedType !== 'reviews' && parsedType !== 'chitchat' && parsedType !== 'unclear' && parsedType !== 'clarify' && Array.isArray(results) && results.length > 0;

            const assistantMsg: ChatMessage = {
                id: `msg_${Date.now() + 1}`,
                sender: 'assistant',
                text: assistantText,
                proposal,
                results: shouldShowResults ? results : undefined,
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

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            handleSend(e as unknown as React.FormEvent);
        }
    };

    const renderMarkdown = (text: string) => {
        // Simple markdown: **bold**, bullet points, line breaks
        const parts = text.split('\n');
        return parts.map((line, i) => {
            let processed = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            const isBullet = /^[•\-]\s/.test(line);
            if (isBullet) {
                processed = processed.replace(/^[•\-]\s/, '');
                return (
                    <div key={i} style={{ display: 'flex', gap: '6px', marginLeft: '4px', marginTop: '2px' }}>
                        <span style={{ color: '#6366f1', flexShrink: 0 }}>•</span>
                        <span dangerouslySetInnerHTML={{ __html: processed }} />
                    </div>
                );
            }
            return (
                <div key={i}>
                    {line === '' ? <br /> : <span dangerouslySetInnerHTML={{ __html: processed }} />}
                </div>
            );
        });
    };

    const handleNewChat = () => {
        setMessages([WELCOME_MESSAGE]);
        setInput('');
    };

    // ─── FAB (closed) ─────────────────────────────────────────────
    if (!isOpen) {
        return (
            <button
                id="copilot-fab"
                onClick={() => setIsOpen(true)}
                onMouseEnter={() => setFabHovered(true)}
                onMouseLeave={() => setFabHovered(false)}
                style={{
                    position: 'fixed',
                    bottom: '24px',
                    right: '24px',
                    zIndex: 99999,
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '16px 28px',
                    fontSize: '15px',
                    fontWeight: 700,
                    color: '#ffffff',
                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%)',
                    borderRadius: '50px',
                    boxShadow: fabHovered
                        ? '0 16px 35px -6px rgba(102, 126, 234, 0.65), 0 12px 18px -8px rgba(0, 0, 0, 0.3), 0 0 20px rgba(240, 147, 251, 0.4)'
                        : '0 12px 28px -6px rgba(102, 126, 234, 0.5), 0 10px 14px -8px rgba(0, 0, 0, 0.25)',
                    border: 'none',
                    cursor: 'pointer',
                    fontFamily: "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif",
                    letterSpacing: '0.4px',
                    transform: fabHovered ? 'translateY(-3px) scale(1.04)' : 'translateY(0) scale(1)',
                    transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                }}
            >
                <span style={{ 
                    fontSize: '20px',
                    filter: 'drop-shadow(0 2px 4px rgba(0, 0, 0, 0.15))',
                }}>✨</span> 
                <span style={{
                    textShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
                }}>Shopping Copilot</span>
            </button>
        );
    }

    // ─── Chat modal (open) ─────────────────────────────────────────
    return (
        <div
            id="copilot-modal"
            style={{
                position: 'fixed',
                bottom: '24px',
                right: '24px',
                zIndex: 99999,
                width: '420px',
                maxWidth: 'calc(100vw - 32px)',
                height: '600px',
                maxHeight: 'calc(100vh - 48px)',
                backgroundColor: '#fafbfc',
                borderRadius: '20px',
                boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(99, 102, 241, 0.1)',
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
                fontFamily: "'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif",
                animation: 'copilotSlideUp 0.35s cubic-bezier(0.16, 1, 0.3, 1)',
            }}
        >
            {/* Inline keyframes */}
            <style>{`
                @keyframes copilotSlideUp {
                    from { opacity: 0; transform: translateY(20px) scale(0.95); }
                    to { opacity: 1; transform: translateY(0) scale(1); }
                }
                @keyframes copilotTypingDot {
                    0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
                    30% { transform: translateY(-4px); opacity: 1; }
                }
                @keyframes copilotPulse {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.6; }
                }
                #copilot-modal textarea::placeholder {
                    color: #9ca3af;
                }
                #copilot-modal textarea:focus {
                    border-color: #818cf8 !important;
                    box-shadow: 0 0 0 3px rgba(129, 140, 248, 0.15) !important;
                }
                #copilot-modal ::-webkit-scrollbar { width: 5px; }
                #copilot-modal ::-webkit-scrollbar-track { background: transparent; }
                #copilot-modal ::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 10px; }
                #copilot-modal ::-webkit-scrollbar-thumb:hover { background: #9ca3af; }
            `}</style>

            {/* ─── Header ─────────────────────────────────────────── */}
            <div
                style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: '16px 20px',
                    background: 'linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%)',
                    color: '#ffffff',
                    fontWeight: 700,
                    fontSize: '15px',
                    letterSpacing: '0.4px',
                    boxShadow: '0 4px 12px rgba(102, 126, 234, 0.3)',
                }}
            >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ 
                        fontSize: '20px',
                        filter: 'drop-shadow(0 2px 4px rgba(0, 0, 0, 0.15))',
                    }}>✨</span>
                    <span style={{
                        textShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
                    }}>Shopping Copilot</span>
                </div>
                <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    <button
                        onClick={handleNewChat}
                        title="Cuộc trò chuyện mới"
                        style={{
                            background: 'rgba(255,255,255,0.15)',
                            border: 'none',
                            color: '#ffffff',
                            fontSize: '13px',
                            cursor: 'pointer',
                            padding: '4px 8px',
                            borderRadius: '6px',
                            display: 'flex',
                            alignItems: 'center',
                            transition: 'background 0.2s',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.25)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.15)')}
                    >
                        🔄
                    </button>
                    <button
                        onClick={() => setIsOpen(false)}
                        aria-label="Close Copilot"
                        style={{
                            background: 'rgba(255,255,255,0.15)',
                            border: 'none',
                            color: '#ffffff',
                            fontSize: '15px',
                            cursor: 'pointer',
                            fontWeight: 'bold',
                            padding: '4px 8px',
                            borderRadius: '6px',
                            lineHeight: 1,
                            transition: 'background 0.2s',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.25)')}
                        onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.15)')}
                    >
                        ✕
                    </button>
                </div>
            </div>

            {/* ─── Messages area ──────────────────────────────────── */}
            <div
                style={{
                    flex: 1,
                    padding: '16px',
                    overflowY: 'auto',
                    backgroundColor: '#f8f9fc',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '12px',
                    fontSize: '13px',
                    lineHeight: '1.5',
                }}
            >
                {messages.map((msg) => (
                    <div
                        key={msg.id}
                        style={{
                            display: 'flex',
                            flexDirection: 'column',
                            alignItems: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                            animation: 'copilotSlideUp 0.25s ease-out',
                        }}
                    >
                        {msg.sender === 'assistant' && (
                            <div style={{ fontSize: '10px', color: '#9ca3af', marginBottom: '4px', marginLeft: '4px', fontWeight: 500 }}>
                                Copilot
                            </div>
                        )}
                        <div
                            style={{
                                padding: '12px 16px',
                                borderRadius: msg.sender === 'user' ? '16px 16px 4px 16px' : '16px 16px 16px 4px',
                                maxWidth: '88%',
                                lineHeight: '1.55',
                                backgroundColor: msg.sender === 'user'
                                    ? 'linear-gradient(135deg, #6366f1, #8b5cf6)'
                                    : '#ffffff',
                                background: msg.sender === 'user'
                                    ? 'linear-gradient(135deg, #6366f1, #8b5cf6)'
                                    : '#ffffff',
                                color: msg.sender === 'user' ? '#ffffff' : '#1f2937',
                                border: msg.sender === 'user' ? 'none' : '1px solid #e8eaef',
                                boxShadow: msg.sender === 'user'
                                    ? '0 2px 8px rgba(99, 102, 241, 0.3)'
                                    : '0 1px 3px rgba(0,0,0,0.04)',
                                wordBreak: 'break-word' as const,
                                overflowWrap: 'break-word' as const,
                                whiteSpace: 'pre-wrap' as const,
                            }}
                        >
                            {msg.sender === 'assistant' ? renderMarkdown(msg.text) : msg.text}
                        </div>
                        {msg.proposal && (
                            <div style={{ width: '100%', marginTop: '6px' }}>
                                <CartActionCard proposal={msg.proposal} />
                            </div>
                        )}
                        {msg.results && msg.results.length > 0 && (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '8px', width: '100%', maxWidth: '92%' }}>
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
                                                gap: '12px',
                                                padding: '12px',
                                                backgroundColor: '#ffffff',
                                                border: '1px solid #e8eaef',
                                                borderRadius: '12px',
                                                textDecoration: 'none',
                                                color: 'inherit',
                                                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                                                cursor: 'pointer',
                                                transition: 'all 0.2s ease',
                                            }}
                                            onMouseEnter={(e) => {
                                                e.currentTarget.style.borderColor = '#818cf8';
                                                e.currentTarget.style.boxShadow = '0 2px 8px rgba(99, 102, 241, 0.12)';
                                            }}
                                            onMouseLeave={(e) => {
                                                e.currentTarget.style.borderColor = '#e8eaef';
                                                e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.04)';
                                            }}
                                        >
                                            {p.picture && (
                                                <img
                                                    src={`/images/products/${p.picture}`}
                                                    alt={p.name}
                                                    style={{
                                                        width: '52px',
                                                        height: '52px',
                                                        objectFit: 'contain',
                                                        borderRadius: '8px',
                                                        backgroundColor: '#f3f4f6',
                                                        flexShrink: 0,
                                                        padding: '4px',
                                                    }}
                                                />
                                            )}
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{
                                                    fontWeight: 600,
                                                    fontSize: '13px',
                                                    color: '#111827',
                                                    overflow: 'hidden',
                                                    textOverflow: 'ellipsis',
                                                    display: '-webkit-box',
                                                    WebkitLineClamp: 2,
                                                    WebkitBoxOrient: 'vertical' as const,
                                                    lineHeight: '1.3',
                                                }}>
                                                    {p.name}
                                                </div>
                                                {priceStr && (
                                                    <div style={{
                                                        fontWeight: 700,
                                                        fontSize: '13px',
                                                        color: '#6366f1',
                                                        marginTop: '4px',
                                                    }}>
                                                        {priceStr}
                                                    </div>
                                                )}
                                            </div>
                                            <div style={{
                                                fontSize: '16px',
                                                color: '#c7c9d1',
                                                flexShrink: 0,
                                            }}>
                                                →
                                            </div>
                                        </a>
                                    );
                                })}
                            </div>
                        )}
                    </div>
                ))}

                {/* Typing indicator */}
                {loading && (
                    <div style={{ display: 'flex', alignItems: 'flex-start', flexDirection: 'column', gap: '4px' }}>
                        <div style={{ fontSize: '10px', color: '#9ca3af', marginLeft: '4px', fontWeight: 500 }}>Copilot</div>
                        <div style={{
                            display: 'flex',
                            gap: '5px',
                            padding: '14px 18px',
                            backgroundColor: '#ffffff',
                            borderRadius: '16px 16px 16px 4px',
                            border: '1px solid #e8eaef',
                            boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                        }}>
                            {[0, 1, 2].map((i) => (
                                <div
                                    key={i}
                                    style={{
                                        width: '7px',
                                        height: '7px',
                                        borderRadius: '50%',
                                        backgroundColor: '#818cf8',
                                        animation: `copilotTypingDot 1.4s ease-in-out ${i * 0.2}s infinite`,
                                    }}
                                />
                            ))}
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* ─── Input area ─────────────────────────────────────── */}
            <form
                onSubmit={handleSend}
                style={{
                    padding: '12px 14px',
                    backgroundColor: '#ffffff',
                    borderTop: '1px solid #ecedf1',
                    display: 'flex',
                    gap: '8px',
                    alignItems: 'flex-end',
                }}
            >
                <textarea
                    ref={textareaRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder='Nhập yêu cầu của bạn... (tìm sản phẩm, xem đánh giá, thêm vào giỏ...)'
                    rows={1}
                    style={{
                        flex: 1,
                        padding: '10px 14px',
                        fontSize: '13px',
                        border: '1px solid #dde0e6',
                        borderRadius: '12px',
                        outline: 'none',
                        resize: 'none',
                        fontFamily: 'inherit',
                        lineHeight: '1.4',
                        maxHeight: '100px',
                        overflowY: 'auto',
                        transition: 'border-color 0.2s, box-shadow 0.2s',
                        backgroundColor: '#f8f9fc',
                    }}
                />
                <button
                    type="submit"
                    disabled={loading || !input.trim()}
                    style={{
                        padding: '10px 16px',
                        fontSize: '14px',
                        fontWeight: 600,
                        color: '#ffffff',
                        background: loading || !input.trim()
                            ? '#c7c9d1'
                            : 'linear-gradient(135deg, #6366f1, #8b5cf6)',
                        border: 'none',
                        borderRadius: '12px',
                        cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
                        transition: 'all 0.2s ease',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        flexShrink: 0,
                        height: '38px',
                        width: '38px',
                    }}
                >
                    ➤
                </button>
            </form>
        </div>
    );
};

export default CopilotChatModal;
