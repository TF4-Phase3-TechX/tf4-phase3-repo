// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
package kafka

import (
	"crypto/sha512"
	"crypto/tls"
	"fmt"
	"hash"
	"log/slog"
	"strings"

	"github.com/IBM/sarama"
	"github.com/xdg-go/scram"
)

var (
	Topic           = "orders"
	ProtocolVersion = sarama.V3_0_0_0
)

type saramaLogger struct {
	logger *slog.Logger
}

type scramClient struct {
	*scram.Client
	*scram.ClientConversation
	hashGenerator func() hash.Hash
}

func (x *scramClient) Begin(userName, password, authzID string) error {
	client, err := scram.NewClient(x.hashGenerator, userName, password, authzID)
	if err != nil {
		return err
	}
	x.Client = client
	x.ClientConversation = client.NewConversation()
	return nil
}

func (x *scramClient) Step(challenge string) (string, error) {
	return x.ClientConversation.Step(challenge)
}

func (x *scramClient) Done() bool {
	return x.ClientConversation.Done()
}

func (l *saramaLogger) Printf(format string, v ...interface{}) {
	l.logger.Info(fmt.Sprintf(format, v...))
}
func (l *saramaLogger) Println(v ...interface{}) {
	l.logger.Info(fmt.Sprint(v...))
}
func (l *saramaLogger) Print(v ...interface{}) {
	l.logger.Info(fmt.Sprint(v...))
}

func CreateKafkaProducer(brokers []string, logger *slog.Logger, securityProtocol, saslMechanism, username, password string) (sarama.AsyncProducer, error) {
	// Set the logger for sarama to use.
	sarama.Logger = &saramaLogger{logger: logger}

	saramaConfig := sarama.NewConfig()
	saramaConfig.Producer.Return.Successes = true
	saramaConfig.Producer.Return.Errors = true

	// Sarama has an issue in a single broker kafka if the kafka broker is restarted.
	// This setting is to prevent that issue from manifesting itself, but may swallow failed messages.
	saramaConfig.Producer.RequiredAcks = sarama.NoResponse

	saramaConfig.Version = ProtocolVersion

	// So we can know the partition and offset of messages.
	saramaConfig.Producer.Return.Successes = true
	if err := applySecurityConfig(saramaConfig, securityProtocol, saslMechanism, username, password); err != nil {
		return nil, err
	}

	producer, err := sarama.NewAsyncProducer(brokers, saramaConfig)
	if err != nil {
		return nil, err
	}

	// We will log to STDOUT if we're not able to produce messages.
	go func() {
		for err := range producer.Errors() {
			logger.Error(fmt.Sprintf("Failed to write message: %+v", err))

		}
	}()
	return producer, nil
}

func applySecurityConfig(config *sarama.Config, securityProtocol, saslMechanism, username, password string) error {
	switch strings.ToUpper(strings.TrimSpace(securityProtocol)) {
	case "":
		return nil
	case "SSL":
		config.Net.TLS.Enable = true
		config.Net.TLS.Config = &tls.Config{MinVersion: tls.VersionTLS12}
		return nil
	case "SASL_SSL":
		config.Net.TLS.Enable = true
		config.Net.TLS.Config = &tls.Config{MinVersion: tls.VersionTLS12}
		config.Net.SASL.Enable = true
	default:
		return fmt.Errorf("unsupported KAFKA_SECURITY_PROTOCOL value: %s", securityProtocol)
	}

	if strings.ToUpper(strings.TrimSpace(saslMechanism)) != "SCRAM-SHA-512" {
		return fmt.Errorf("unsupported KAFKA_SASL_MECHANISM value: %s", saslMechanism)
	}
	if username == "" {
		return fmt.Errorf("KAFKA_USERNAME is required for SASL_SSL Kafka")
	}
	if password == "" {
		return fmt.Errorf("KAFKA_PASSWORD is required for SASL_SSL Kafka")
	}

	config.Net.SASL.User = username
	config.Net.SASL.Password = password
	config.Net.SASL.Mechanism = sarama.SASLTypeSCRAMSHA512
	config.Net.SASL.SCRAMClientGeneratorFunc = func() sarama.SCRAMClient {
		return &scramClient{hashGenerator: sha512.New}
	}
	return nil
}
