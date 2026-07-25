// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
package kafka

import (
	"crypto/tls"
	"fmt"
	"log/slog"
	"os"

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

func (l *saramaLogger) Printf(format string, v ...interface{}) {
	l.logger.Info(fmt.Sprintf(format, v...))
}
func (l *saramaLogger) Println(v ...interface{}) {
	l.logger.Info(fmt.Sprint(v...))
}
func (l *saramaLogger) Print(v ...interface{}) {
	l.logger.Info(fmt.Sprint(v...))
}

type scramClient struct {
	hashGenerator scram.HashGeneratorFcn
	*scram.Client
	*scram.ClientConversation
}

func (x *scramClient) Begin(userName, password, authzID string) error {
	client, err := x.hashGenerator.NewClient(userName, password, authzID)
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

func CreateKafkaProducer(brokers []string, logger *slog.Logger) (sarama.AsyncProducer, error) {
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
	if err := applySecurityConfig(saramaConfig); err != nil {
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

func applySecurityConfig(config *sarama.Config) error {
	securityProtocol := os.Getenv("KAFKA_SECURITY_PROTOCOL")
	saslMechanism := os.Getenv("KAFKA_SASL_MECHANISM")
	username := os.Getenv("KAFKA_USERNAME")
	password := os.Getenv("KAFKA_PASSWORD")

	if securityProtocol == "" && saslMechanism == "" && username == "" && password == "" {
		return nil
	}

	if username == "" || password == "" {
		return fmt.Errorf("KAFKA_USERNAME and KAFKA_PASSWORD must be set when Kafka SASL is enabled")
	}

	switch securityProtocol {
	case "", "SASL_SSL":
		config.Net.TLS.Enable = true
		config.Net.TLS.Config = &tls.Config{MinVersion: tls.VersionTLS12}
	case "SASL_PLAINTEXT":
	default:
		return fmt.Errorf("unsupported KAFKA_SECURITY_PROTOCOL value: %s", securityProtocol)
	}

	config.Net.SASL.Enable = true
	config.Net.SASL.User = username
	config.Net.SASL.Password = password

	switch saslMechanism {
	case "", "SCRAM-SHA-512":
		config.Net.SASL.Mechanism = sarama.SASLTypeSCRAMSHA512
		config.Net.SASL.SCRAMClientGeneratorFunc = func() sarama.SCRAMClient {
			return &scramClient{hashGenerator: scram.SHA512}
		}
	case "SCRAM-SHA-256":
		config.Net.SASL.Mechanism = sarama.SASLTypeSCRAMSHA256
		config.Net.SASL.SCRAMClientGeneratorFunc = func() sarama.SCRAMClient {
			return &scramClient{hashGenerator: scram.SHA256}
		}
	case "PLAIN":
		config.Net.SASL.Mechanism = sarama.SASLTypePlaintext
	default:
		return fmt.Errorf("unsupported KAFKA_SASL_MECHANISM value: %s", saslMechanism)
	}
	return nil
}
