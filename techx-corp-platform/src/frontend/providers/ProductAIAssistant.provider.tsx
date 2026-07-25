// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { createContext, useContext, useEffect, useMemo } from 'react';
import { useMutation, MutateOptions } from '@tanstack/react-query';
import ApiGateway from '../gateways/Api.gateway';
import SessionGateway from '../gateways/Session.gateway';
import { v4 } from 'uuid';

export interface AiRequestPayload {
    question: string;
}

export type AiResponse = { response?: string; text?: string; actionProposal?: any } | string;

interface AiAssistantContextValue {
    aiResponse: AiResponse | null;
    aiLoading: boolean;
    aiError: Error | null;
    sessionId: string;
    userId: string;
    sendAiRequest: (
        payload: AiRequestPayload,
        options?: MutateOptions<AiResponse, Error, AiRequestPayload, unknown>
    ) => void;
    reset: () => void;
}

const Context = createContext<AiAssistantContextValue>({
    aiResponse: null,
    aiLoading: false,
    aiError: null,
    sessionId: '',
    userId: '',
    sendAiRequest: () => {},
    reset: () => {},
});

export const useAiAssistant = () => useContext(Context);

interface ProductAIAssistantProviderProps {
    children: React.ReactNode;
    productId: string;
}

const ProductAIAssistantProvider = ({ children, productId }: ProductAIAssistantProviderProps) => {
    const sessionId = useMemo(() => v4(), []);
    const userId = useMemo(() => SessionGateway.getSession().userId, []);
    const mutation = useMutation<AiResponse, Error, AiRequestPayload>({
        mutationFn: ({ question }) => ApiGateway.askProductAIAssistant(productId, question, sessionId, userId),
    });

    // Clear AI state when switching products.
    useEffect(() => {
        mutation.reset();
    }, [productId]);

    const value = useMemo(
        () => ({
            aiResponse: mutation.data ?? null,
            aiLoading: mutation.isPending,
            aiError: mutation.error ?? null,
            sessionId,
            userId,
            sendAiRequest: (
                payload: AiRequestPayload,
                options?: MutateOptions<AiResponse, Error, AiRequestPayload, unknown>
            ) => {
                mutation.mutate(payload, options);
            },
            reset: () => mutation.reset(),
        }),
        [mutation.data, mutation.isPending, mutation.error, sessionId, userId]
    );

    return <Context.Provider value={value}>{children}</Context.Provider>;
};

export default ProductAIAssistantProvider;
