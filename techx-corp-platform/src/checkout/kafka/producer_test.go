// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
package kafka

import (
	"testing"

	"github.com/IBM/sarama"
)

func TestNewProducerConfig_UsesAckCompatibleWithSuccesses(t *testing.T) {
	t.Setenv("KAFKA_SECURITY_PROTOCOL", "")
	t.Setenv("KAFKA_SASL_MECHANISM", "")
	t.Setenv("KAFKA_USERNAME", "")
	t.Setenv("KAFKA_PASSWORD", "")

	config, err := newProducerConfig()
	if err != nil {
		t.Fatalf("newProducerConfig returned error: %v", err)
	}

	if !config.Producer.Return.Successes {
		t.Fatal("expected producer successes to be enabled")
	}
	if !config.Producer.Return.Errors {
		t.Fatal("expected producer errors to be enabled")
	}
	if config.Producer.RequiredAcks == sarama.NoResponse {
		t.Fatal("RequiredAcks=NoResponse is incompatible with waiting for producer success offsets")
	}
	if err := config.Validate(); err != nil {
		t.Fatalf("producer config should validate: %v", err)
	}
}
