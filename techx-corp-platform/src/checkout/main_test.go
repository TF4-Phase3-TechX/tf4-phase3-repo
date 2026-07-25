// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
package main

import (
	"context"
	"io"
	"log/slog"
	"testing"

	pb "github.com/open-telemetry/techx-corp/src/checkout/genproto/oteldemo"
)

// Regression test for the panic that took down checkout during the REL-17
// Kafka MSK cutover: sendToPostProcessor used to call
// cs.KafkaProducerClient.Input() unconditionally, so any request that arrived
// before the producer connected (or after it failed to connect) crashed the
// whole process with a nil pointer dereference.
func TestSendToPostProcessor_NilProducer_DoesNotPanic(t *testing.T) {
	logger = slog.New(slog.NewTextHandler(io.Discard, nil))

	cs := &checkout{}
	// KafkaProducerClient intentionally left nil - simulates the producer
	// not having connected yet (or a failed/retrying connection).

	defer func() {
		if r := recover(); r != nil {
			t.Fatalf("sendToPostProcessor panicked with nil producer: %v", r)
		}
	}()

	cs.sendToPostProcessor(context.Background(), &pb.OrderResult{})
}

func TestGetSetKafkaProducer_NilByDefault(t *testing.T) {
	cs := &checkout{}
	if p := cs.getKafkaProducer(); p != nil {
		t.Fatalf("expected nil producer before connectKafkaProducerWithRetry runs, got %v", p)
	}
}
