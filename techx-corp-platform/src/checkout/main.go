// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/log/global"
	semconv "go.opentelemetry.io/otel/semconv/v1.24.0"
	"go.opentelemetry.io/otel/trace"

	"github.com/IBM/sarama"
	"github.com/google/uuid"
	otelhooks "github.com/open-feature/go-sdk-contrib/hooks/open-telemetry/pkg"
	flagd "github.com/open-feature/go-sdk-contrib/providers/flagd/pkg"
	"github.com/open-feature/go-sdk/openfeature"

	"go.opentelemetry.io/contrib/bridges/otelslog"
	"go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc"
	"go.opentelemetry.io/contrib/instrumentation/net/http/otelhttp"
	"go.opentelemetry.io/contrib/instrumentation/runtime"
	"go.opentelemetry.io/otel"
	otelcodes "go.opentelemetry.io/otel/codes"
	"go.opentelemetry.io/otel/exporters/otlp/otlplog/otlploggrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlpmetric/otlpmetricgrpc"
	"go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc"
	"go.opentelemetry.io/otel/propagation"

	sdklog "go.opentelemetry.io/otel/sdk/log"
	sdkmetric "go.opentelemetry.io/otel/sdk/metric"
	sdkresource "go.opentelemetry.io/otel/sdk/resource"
	sdktrace "go.opentelemetry.io/otel/sdk/trace"

	"google.golang.org/grpc"
	"google.golang.org/grpc/backoff"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/credentials/insecure"
	"google.golang.org/grpc/health"
	healthpb "google.golang.org/grpc/health/grpc_health_v1"
	"google.golang.org/grpc/status"
	"google.golang.org/protobuf/proto"

	pb "github.com/open-telemetry/techx-corp/src/checkout/genproto/oteldemo"
	"github.com/open-telemetry/techx-corp/src/checkout/kafka"
	"github.com/open-telemetry/techx-corp/src/checkout/money"
)

//go:generate go install google.golang.org/protobuf/cmd/protoc-gen-go
//go:generate go install google.golang.org/grpc/cmd/protoc-gen-go-grpc
//go:generate protoc --go_out=./ --go-grpc_out=./ --proto_path=../../pb ../../pb/demo.proto

var logger *slog.Logger
var tracer trace.Tracer
var resource *sdkresource.Resource
var initResourcesOnce sync.Once

func initResource() *sdkresource.Resource {
	initResourcesOnce.Do(func() {
		extraResources, _ := sdkresource.New(
			context.Background(),
			sdkresource.WithOS(),
			sdkresource.WithProcess(),
			sdkresource.WithContainer(),
			sdkresource.WithHost(),
		)
		resource, _ = sdkresource.Merge(
			sdkresource.Default(),
			extraResources,
		)
	})
	return resource
}

func initTracerProvider() *sdktrace.TracerProvider {
	ctx := context.Background()

	exporter, err := otlptracegrpc.New(ctx)
	if err != nil {
		logger.Error(fmt.Sprintf("new otlp trace grpc exporter failed: %v", err))
	}
	tp := sdktrace.NewTracerProvider(
		sdktrace.WithBatcher(exporter),
		sdktrace.WithResource(initResource()),
	)
	otel.SetTracerProvider(tp)
	otel.SetTextMapPropagator(propagation.NewCompositeTextMapPropagator(propagation.TraceContext{}, propagation.Baggage{}))
	return tp
}

func initMeterProvider() *sdkmetric.MeterProvider {
	ctx := context.Background()

	exporter, err := otlpmetricgrpc.New(ctx)
	if err != nil {
		logger.Error(fmt.Sprintf("new otlp metric grpc exporter failed: %v", err))
	}

	mp := sdkmetric.NewMeterProvider(
		sdkmetric.WithReader(sdkmetric.NewPeriodicReader(exporter)),
		sdkmetric.WithResource(initResource()),
	)
	otel.SetMeterProvider(mp)
	return mp
}

func initLoggerProvider() *sdklog.LoggerProvider {
	ctx := context.Background()

	logExporter, err := otlploggrpc.New(ctx)
	if err != nil {
		return nil
	}

	loggerProvider := sdklog.NewLoggerProvider(
		sdklog.WithProcessor(sdklog.NewBatchProcessor(logExporter)),
	)
	global.SetLoggerProvider(loggerProvider)

	return loggerProvider
}

type checkout struct {
	productCatalogSvcAddr string
	cartSvcAddr           string
	currencySvcAddr       string
	shippingSvcAddr       string
	emailSvcAddr          string
	paymentSvcAddr        string
	kafkaBrokerSvcAddr    string
	pb.UnimplementedCheckoutServiceServer
	kafkaProducerMu         sync.RWMutex
	KafkaProducerClient     sarama.AsyncProducer
	shippingSvcClient       pb.ShippingServiceClient
	productCatalogSvcClient pb.ProductCatalogServiceClient
	cartSvcClient           pb.CartServiceClient
	currencySvcClient       pb.CurrencyServiceClient
	emailSvcClient          pb.EmailServiceClient
	paymentSvcClient        pb.PaymentServiceClient
}

// getKafkaProducer returns the current producer, or nil if it hasn't connected
// yet (or hasn't reconnected after a failure). Safe for concurrent use with
// setKafkaProducer, which the background retry loop calls from another goroutine.
func (cs *checkout) getKafkaProducer() sarama.AsyncProducer {
	cs.kafkaProducerMu.RLock()
	defer cs.kafkaProducerMu.RUnlock()
	return cs.KafkaProducerClient
}

func (cs *checkout) setKafkaProducer(p sarama.AsyncProducer) {
	cs.kafkaProducerMu.Lock()
	defer cs.kafkaProducerMu.Unlock()
	cs.KafkaProducerClient = p
}

// connectKafkaProducerWithRetry keeps trying to create the Kafka producer with
// capped exponential backoff until it succeeds. Runs in the background so a
// slow/unreachable broker (e.g. MSK SASL_SSL handshake taking longer than
// self-hosted plaintext, or a transient outage) never blocks service startup
// or crashes the process — sendToPostProcessor treats a nil producer as
// "not connected yet" and skips the Kafka publish for that order instead of
// panicking.
func (cs *checkout) connectKafkaProducerWithRetry(logger *slog.Logger) {
	delay := 2 * time.Second
	const maxDelay = 30 * time.Second
	for {
		producer, err := kafka.CreateKafkaProducer([]string{cs.kafkaBrokerSvcAddr}, logger)
		if err == nil {
			cs.setKafkaProducer(producer)
			logger.Info("Kafka producer connected")
			return
		}
		logger.Error(fmt.Sprintf("Failed to create Kafka producer, retrying in %v: %v", delay, err))
		time.Sleep(delay)
		delay *= 2
		if delay > maxDelay {
			delay = maxDelay
		}
	}
}

func main() {
	var port string
	mustMapEnv(&port, "CHECKOUT_PORT")

	tp := initTracerProvider()
	defer func() {
		if err := tp.Shutdown(context.Background()); err != nil {
			logger.Error(fmt.Sprintf("Error shutting down tracer provider: %v", err))
		}
	}()

	mp := initMeterProvider()
	defer func() {
		if err := mp.Shutdown(context.Background()); err != nil {
			logger.Error(fmt.Sprintf("Error shutting down meter provider: %v", err))
		}
	}()

	lp := initLoggerProvider()
	defer func() {
		if err := lp.Shutdown(context.Background()); err != nil {
			logger.Error(fmt.Sprintf("Error shutting down logger provider: %v", err))
		}
	}()

	// this *must* be called after the logger provider is initialized
	// otherwise the Sarama producer in kafka/producer.go will not be
	// able to log properly
	logger = otelslog.NewLogger("checkout")
	slog.SetDefault(logger)

	err := runtime.Start(runtime.WithMinimumReadMemStatsInterval(time.Second))
	if err != nil {
		logger.Error((err.Error()))
	}

	provider, err := flagd.NewProvider()
	if err != nil {
		logger.Error(fmt.Sprintf("Error creating flagd provider: %v", err))
	}

	openfeature.SetProvider(provider)
	openfeature.AddHooks(otelhooks.NewTracesHook())

	tracer = tp.Tracer("checkout")

	svc := new(checkout)

	mustMapEnv(&svc.shippingSvcAddr, "SHIPPING_ADDR")
	c := mustCreateClient(svc.shippingSvcAddr)
	svc.shippingSvcClient = pb.NewShippingServiceClient(c)
	defer c.Close()

	mustMapEnv(&svc.productCatalogSvcAddr, "PRODUCT_CATALOG_ADDR")
	c = mustCreateClient(svc.productCatalogSvcAddr)
	svc.productCatalogSvcClient = pb.NewProductCatalogServiceClient(c)
	defer c.Close()

	mustMapEnv(&svc.cartSvcAddr, "CART_ADDR")
	c = mustCreateClient(svc.cartSvcAddr)
	svc.cartSvcClient = pb.NewCartServiceClient(c)
	defer c.Close()

	mustMapEnv(&svc.currencySvcAddr, "CURRENCY_ADDR")
	c = mustCreateClient(svc.currencySvcAddr)
	svc.currencySvcClient = pb.NewCurrencyServiceClient(c)
	defer c.Close()

	mustMapEnv(&svc.emailSvcAddr, "EMAIL_ADDR")
	c = mustCreateClient(svc.emailSvcAddr)
	svc.emailSvcClient = pb.NewEmailServiceClient(c)
	defer c.Close()

	mustMapEnv(&svc.paymentSvcAddr, "PAYMENT_ADDR")
	c = mustCreateClient(svc.paymentSvcAddr)
	svc.paymentSvcClient = pb.NewPaymentServiceClient(c)
	defer c.Close()

	svc.kafkaBrokerSvcAddr = os.Getenv("KAFKA_ADDR")

	if svc.kafkaBrokerSvcAddr != "" {
		go svc.connectKafkaProducerWithRetry(logger)
	}

	logger.Info(fmt.Sprintf("service config: %+v", svc))

	lis, err := net.Listen("tcp", fmt.Sprintf(":%s", port))
	if err != nil {
		logger.Error(err.Error())
	}

	var srv = grpc.NewServer(
		grpc.StatsHandler(otelgrpc.NewServerHandler()),
	)
	pb.RegisterCheckoutServiceServer(srv, svc)

	healthcheck := health.NewServer()
	healthpb.RegisterHealthServer(srv, healthcheck)
	logger.Info(fmt.Sprintf("starting to listen on tcp: %q", lis.Addr().String()))
	err = srv.Serve(lis)
	logger.Error(err.Error())

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM, syscall.SIGKILL)
	defer cancel()

	go func() {
		if err := srv.Serve(lis); err != nil {
			logger.Error(err.Error())
		}
	}()

	<-ctx.Done()

	srv.GracefulStop()
	logger.Info("Checkout gRPC server stopped")
}

func mustMapEnv(target *string, envKey string) {
	v := os.Getenv(envKey)
	if v == "" {
		panic(fmt.Sprintf("environment variable %q not set", envKey))
	}
	*target = v
}

func (cs *checkout) Check(ctx context.Context, req *healthpb.HealthCheckRequest) (*healthpb.HealthCheckResponse, error) {
	return &healthpb.HealthCheckResponse{Status: healthpb.HealthCheckResponse_SERVING}, nil
}

func (cs *checkout) Watch(req *healthpb.HealthCheckRequest, ws healthpb.Health_WatchServer) error {
	return status.Errorf(codes.Unimplemented, "health check via Watch not implemented")
}

// retryRead chạy một lời gọi IDEMPOTENT với timeout cho mỗi attempt và tối đa 1
// retry. Backoff tôn trọng ctx cha (không sleep khi ctx đã done).
// CHỈ dùng cho read (cart, product-catalog, currency, get-quote).
// TUYỆT ĐỐI không dùng cho call có side effect (payment, ship-order).
func retryRead(ctx context.Context, perAttempt, backoff time.Duration, fn func(ctx context.Context) error) error {
	var err error
	for attempt := 0; attempt < 2; attempt++ {
		callCtx, cancel := context.WithTimeout(ctx, perAttempt)
		err = fn(callCtx)
		cancel()
		if err == nil {
			return nil
		}
		if attempt == 0 {
			select {
			case <-time.After(backoff):
			case <-ctx.Done():
				return ctx.Err() // ctx cha cancel/hết hạn → dừng, không sleep tiếp
			}
		}
	}
	return err
}

func (cs *checkout) PlaceOrder(ctx context.Context, req *pb.PlaceOrderRequest) (*pb.PlaceOrderResponse, error) {
	userCurrency, err := normalizeCurrencyCode(req.GetUserCurrency())
	if err != nil {
		return nil, status.Error(codes.InvalidArgument, err.Error())
	}

	// Overall deadline: trần chống-treo cho toàn request (không phải mục tiêu SLO).
	// Configurable qua env để tune không cần rebuild; mặc định 20s.
	overall := 20 * time.Second
	if v := os.Getenv("CHECKOUT_OVERALL_TIMEOUT"); v != "" {
		if d, perr := time.ParseDuration(v); perr == nil {
			overall = d
		}
	}
	ctx, cancel := context.WithTimeout(ctx, overall)
	defer cancel()

	span := trace.SpanFromContext(ctx)
	span.SetAttributes(
		attribute.String("app.user.id", req.UserId),
		attribute.String("app.user.currency", userCurrency),
	)
	logger.LogAttrs(
		ctx,
		slog.LevelInfo, "[PlaceOrder]",
		slog.String("user_id", req.UserId),
		slog.String("user_currency", userCurrency),
	)

	defer func() {
		if err != nil {
			span.AddEvent("error", trace.WithAttributes(semconv.ExceptionMessageKey.String(err.Error())))
		}
	}()

	orderID, err := uuid.NewUUID()
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to generate order uuid")
	}

	prep, err := cs.prepareOrderItemsAndShippingQuoteFromCart(ctx, req.UserId, userCurrency, req.Address)
	if err != nil {
		return nil, checkoutStatusError(err)
	}
	span.AddEvent("prepared")

	total := &pb.Money{CurrencyCode: userCurrency}
	total, err = money.Sum(total, prep.shippingCostLocalized)
	if err != nil {
		return nil, status.Error(codes.Internal, "invalid shipping cost")
	}
	for _, it := range prep.orderItems {
		multPrice, multiplyErr := multiplyMoney(it.Cost, it.GetItem().GetQuantity())
		if multiplyErr != nil {
			return nil, status.Errorf(codes.Internal, "invalid item cost: %v", multiplyErr)
		}
		total, err = money.Sum(total, multPrice)
		if err != nil {
			return nil, status.Error(codes.Internal, "invalid order total")
		}
	}

	// Chỉ bắt đầu payment nếu còn ĐỦ budget cho toàn bộ write path (payment 5s + ship 3s).
	// Không dùng ctx.Err() đơn thuần — nó chỉ bắt ctx đã hết hạn hẳn, không bắt ctx sắp hết,
	// nên không chặn được trường hợp overall deadline cháy GIỮA LÚC Charge đang chạy
	// (RPC bị cancel client-side nhưng payment server có thể đã trừ tiền).
	const writePathBudget = 8 * time.Second // payment 5s + ship-order 3s (§4.1)
	if dl, ok := ctx.Deadline(); ok && time.Until(dl) < writePathBudget {
		return nil, status.Errorf(codes.DeadlineExceeded,
			"insufficient budget for payment+shipping (need %s); aborting before charge", writePathBudget)
	}

	txID, err := cs.chargeCard(ctx, total, req.CreditCard)
	if err != nil {
		return nil, status.Errorf(codes.Internal, "failed to charge card: %+v", err)
	}

	span.AddEvent("charged",
		trace.WithAttributes(attribute.String("app.payment.transaction.id", txID)))
	logger.LogAttrs(
		ctx,
		slog.LevelInfo, "payment went through",
		slog.String("transaction_id", txID),
	)

	shippingTrackingID, err := cs.shipOrder(ctx, req.Address, prep.cartItems)
	if err != nil {
		return nil, status.Errorf(codes.Unavailable, "shipping error: %+v", err)
	}
	shippingTrackingAttribute := attribute.String("app.shipping.tracking.id", shippingTrackingID)
	span.AddEvent("shipped", trace.WithAttributes(shippingTrackingAttribute))

	_ = cs.emptyUserCart(ctx, req.UserId)

	orderResult := &pb.OrderResult{
		OrderId:            orderID.String(),
		ShippingTrackingId: shippingTrackingID,
		ShippingCost:       prep.shippingCostLocalized,
		ShippingAddress:    req.Address,
		Items:              prep.orderItems,
	}

	shippingCostFloat, _ := strconv.ParseFloat(fmt.Sprintf("%d.%02d", prep.shippingCostLocalized.GetUnits(), prep.shippingCostLocalized.GetNanos()/1000000000), 64)
	totalPriceFloat, _ := strconv.ParseFloat(fmt.Sprintf("%d.%02d", total.GetUnits(), total.GetNanos()/1000000000), 64)

	span.SetAttributes(
		attribute.String("app.order.id", orderID.String()),
		attribute.Float64("app.shipping.amount", shippingCostFloat),
		attribute.Float64("app.order.amount", totalPriceFloat),
		attribute.Int("app.order.items.count", len(prep.orderItems)),
		shippingTrackingAttribute,
	)
	logger.LogAttrs(
		ctx,
		slog.LevelInfo, "order placed",
		slog.String("app.order.id", orderID.String()),
		slog.Float64("app.shipping.amount", shippingCostFloat),
		slog.Float64("app.order.amount", totalPriceFloat),
		slog.Int("app.order.items.count", len(prep.orderItems)),
		slog.String("app.shipping.tracking.id", shippingTrackingID),
	)

	if err := cs.sendOrderConfirmation(ctx, req.Email, orderResult); err != nil {
		logger.Warn(fmt.Sprintf("failed to send order confirmation to %q: %+v", req.Email, err))
	} else {
		logger.Info(fmt.Sprintf("order confirmation email sent to %q", req.Email))
	}

	// send to kafka only if kafka broker address is set
	if cs.kafkaBrokerSvcAddr != "" {
		logger.Info("sending to postProcessor")
		cs.sendToPostProcessor(ctx, orderResult)
	}

	resp := &pb.PlaceOrderResponse{Order: orderResult}
	return resp, nil
}

type orderPrep struct {
	orderItems            []*pb.OrderItem
	cartItems             []*pb.CartItem
	shippingCostLocalized *pb.Money
}

type orderItemsResult struct {
	items []*pb.OrderItem
	err   error
}

type shippingCostResult struct {
	cost *pb.Money
	err  error
}

func (cs *checkout) prepareOrderItemsAndShippingQuoteFromCart(ctx context.Context, userID, userCurrency string, address *pb.Address) (orderPrep, error) {
	ctx, span := tracer.Start(ctx, "prepareOrderItemsAndShippingQuoteFromCart")
	defer span.End()

	var out orderPrep
	cartItems, err := cs.getUserCart(ctx, userID)
	if err != nil {
		return out, fmt.Errorf("cart failure: %w", err)
	}

	prepCtx, cancel := context.WithCancel(ctx)
	defer cancel()
	orderItemsCh := make(chan orderItemsResult, 1)
	shippingCostCh := make(chan shippingCostResult, 1)

	go func() {
		items, prepErr := cs.prepOrderItems(prepCtx, cartItems, userCurrency)
		orderItemsCh <- orderItemsResult{items: items, err: prepErr}
	}()
	go func() {
		shippingUSD, quoteErr := cs.quoteShipping(prepCtx, address, cartItems)
		if quoteErr != nil {
			shippingCostCh <- shippingCostResult{err: quoteErr}
			return
		}
		if err := validateUSDMoney(shippingUSD); err != nil {
			shippingCostCh <- shippingCostResult{err: fmt.Errorf("invalid shipping quote: %w", err)}
			return
		}
		cost, convertErr := cs.convertCurrency(prepCtx, shippingUSD, userCurrency)
		if convertErr == nil {
			convertErr = validateMoneyInCurrency(cost, userCurrency)
		}
		shippingCostCh <- shippingCostResult{cost: cost, err: convertErr}
	}()

	var orderItems []*pb.OrderItem
	var shippingPrice *pb.Money
	var firstPrepErr error
	for completed := 0; completed < 2; completed++ {
		select {
		case result := <-orderItemsCh:
			orderItems = result.items
			if result.err != nil && firstPrepErr == nil {
				firstPrepErr = fmt.Errorf("failed to prepare order: %w", result.err)
				cancel()
			}
		case result := <-shippingCostCh:
			shippingPrice = result.cost
			if result.err != nil && firstPrepErr == nil {
				firstPrepErr = fmt.Errorf("shipping quote or currency conversion failure: %w", result.err)
				cancel()
			}
		}
	}
	if firstPrepErr != nil {
		return out, firstPrepErr
	}

	out.shippingCostLocalized = shippingPrice
	out.cartItems = cartItems
	out.orderItems = orderItems

	var totalCart int32
	for _, ci := range cartItems {
		totalCart += ci.Quantity
	}
	shippingCostFloat, _ := strconv.ParseFloat(fmt.Sprintf("%d.%02d", shippingPrice.GetUnits(), shippingPrice.GetNanos()/1000000000), 64)
	span.SetAttributes(
		attribute.Float64("app.shipping.amount", shippingCostFloat),
		attribute.Int("app.cart.items.count", int(totalCart)),
		attribute.Int("app.order.items.count", len(orderItems)),
	)
	return out, nil
}

func mustCreateClient(svcAddr string) *grpc.ClientConn {
	c, err := grpc.NewClient(svcAddr,
		grpc.WithTransportCredentials(insecure.NewCredentials()),
		grpc.WithStatsHandler(otelgrpc.NewClientHandler()),
		// WithConnectTimeout đã bị xóa khỏi grpc-go (chỉ tồn tại ở bản rất cũ);
		// WithConnectParams.MinConnectTimeout là API hiện hành tương đương —
		// giới hạn thời gian mỗi lần thử connect trước khi backoff/attempt tiếp theo.
		// Phải set Backoff tường minh (backoff.DefaultConfig) — nếu bỏ trống,
		// ConnectParams.Backoff là zero-value (không phải default), tắt mất backoff thật.
		grpc.WithConnectParams(grpc.ConnectParams{
			Backoff:           backoff.DefaultConfig,
			MinConnectTimeout: 3 * time.Second,
		}),
	)
	if err != nil {
		logger.Error(fmt.Sprintf("could not connect to %s service, err: %+v", svcAddr, err))
	}

	return c
}

func (cs *checkout) quoteShipping(ctx context.Context, address *pb.Address, items []*pb.CartItem) (*pb.Money, error) {
	quotePayload, err := json.Marshal(map[string]interface{}{
		"address": address,
		"items":   items,
	})
	if err != nil {
		return nil, fmt.Errorf("failed to marshal ship order request: %+v", err)
	}

	var shippingQuoteBytes []byte
	var quoteStatusCode int
	err = retryRead(ctx, 3*time.Second, 300*time.Millisecond, func(callCtx context.Context) error {
		// body reader MỚI mỗi attempt — attempt trước đã consume reader cũ.
		resp, e := otelhttp.Post(callCtx, cs.shippingSvcAddr+"/get-quote", "application/json", bytes.NewReader(quotePayload))
		if e != nil {
			return e
		}
		defer resp.Body.Close()
		// Đọc body NGAY TRONG attempt: callCtx bị cancel khi retryRead trả về,
		// mà ctx của HTTP request bao trùm cả việc đọc body — đọc body sau khi
		// cancel sẽ lỗi "context canceled".
		body, e := io.ReadAll(resp.Body)
		if e != nil {
			return e
		}
		quoteStatusCode = resp.StatusCode
		shippingQuoteBytes = body
		return nil
	})
	if err != nil {
		return nil, fmt.Errorf("failed POST to shipping service: %+v", err)
	}

	if quoteStatusCode != http.StatusOK {
		return nil, fmt.Errorf("failed POST to shipping quote service: expected 200, got %d", quoteStatusCode)
	}

	var quoteResp struct {
		CostUsd *pb.Money `json:"cost_usd"`
	}
	if err := json.Unmarshal(shippingQuoteBytes, &quoteResp); err != nil {
		return nil, fmt.Errorf("failed to unmarshal shipping quote: %+v", err)
	}
	if quoteResp.CostUsd == nil {
		return nil, fmt.Errorf("shipping quote missing cost_usd field")
	}

	return quoteResp.CostUsd, nil
}

func (cs *checkout) getUserCart(ctx context.Context, userID string) ([]*pb.CartItem, error) {
	var cart *pb.Cart
	err := retryRead(ctx, 2*time.Second, 200*time.Millisecond, func(callCtx context.Context) error {
		var e error
		cart, e = cs.cartSvcClient.GetCart(callCtx, &pb.GetCartRequest{UserId: userID})
		return e
	})
	if err != nil {
		return nil, fmt.Errorf("failed to get user cart during checkout: %+v", err)
	}
	return cart.GetItems(), nil
}

func (cs *checkout) emptyUserCart(ctx context.Context, userID string) error {
	if _, err := cs.cartSvcClient.EmptyCart(ctx, &pb.EmptyCartRequest{UserId: userID}); err != nil {
		return fmt.Errorf("failed to empty user cart during checkout: %+v", err)
	}
	return nil
}

func (cs *checkout) prepOrderItems(ctx context.Context, items []*pb.CartItem, userCurrency string) ([]*pb.OrderItem, error) {
	products := make([]*pb.Product, len(items))
	if err := cs.getProducts(ctx, items, products); err != nil {
		return nil, err
	}

	prices := make([]*pb.Money, len(items))
	for i, product := range products {
		if err := validateUSDMoney(product.GetPriceUsd()); err != nil {
			return nil, fmt.Errorf("invalid price for product #%q: %w", items[i].GetProductId(), err)
		}
		prices[i] = product.GetPriceUsd()
	}

	var converted []*pb.Money
	var err error
	if userCurrency == "USD" {
		converted = make([]*pb.Money, len(prices))
		for i, price := range prices {
			converted[i], err = cs.convertCurrency(ctx, price, userCurrency)
			if err != nil {
				return nil, fmt.Errorf("failed to convert price of %q to %s: %w", items[i].GetProductId(), userCurrency, err)
			}
			if err := validateMoneyInCurrency(converted[i], userCurrency); err != nil {
				return nil, fmt.Errorf("invalid converted price for product #%q: %w", items[i].GetProductId(), err)
			}
			converted[i] = copyMoney(converted[i])
		}
	} else {
		converted, err = cs.batchConvertCurrency(ctx, prices, userCurrency)
		if err != nil {
			return nil, err
		}
	}
	out := make([]*pb.OrderItem, len(items))
	for i, item := range items {
		out[i] = &pb.OrderItem{Item: item, Cost: converted[i]}
	}
	return out, nil
}

func (cs *checkout) getProducts(ctx context.Context, items []*pb.CartItem, products []*pb.Product) error {
	for i, item := range items {
		product, err := cs.getProduct(ctx, item.GetProductId())
		if err != nil {
			return fmt.Errorf("failed to get product #%q: %w", item.GetProductId(), err)
		}
		if product == nil {
			return fmt.Errorf("product #%q response is empty", item.GetProductId())
		}
		products[i] = product
	}
	return nil
}

func (cs *checkout) getProduct(ctx context.Context, productID string) (*pb.Product, error) {
	var product *pb.Product
	err := retryRead(ctx, time.Second, 100*time.Millisecond, func(callCtx context.Context) error {
		var callErr error
		product, callErr = cs.productCatalogSvcClient.GetProduct(callCtx, &pb.GetProductRequest{Id: productID})
		return callErr
	})
	if err != nil {
		return nil, err
	}
	return product, nil
}

func (cs *checkout) batchConvertCurrency(ctx context.Context, from []*pb.Money, toCurrency string) ([]*pb.Money, error) {
	var response *pb.BatchCurrencyConversionResponse
	err := retryRead(ctx, time.Second, 100*time.Millisecond, func(callCtx context.Context) error {
		var callErr error
		response, callErr = cs.currencySvcClient.BatchConvert(callCtx, &pb.BatchCurrencyConversionRequest{
			From:   from,
			ToCode: toCurrency,
		})
		return callErr
	})
	if err != nil {
		return nil, fmt.Errorf("failed to batch convert item prices: %w", err)
	}
	if response == nil || len(response.GetConverted()) != len(from) {
		return nil, status.Error(codes.Internal, "currency batch response cardinality mismatch")
	}
	converted := make([]*pb.Money, len(from))
	for i, value := range response.GetConverted() {
		if err := validateMoneyInCurrency(value, toCurrency); err != nil {
			return nil, fmt.Errorf("invalid currency batch output #%d: %w", i, err)
		}
		converted[i] = copyMoney(value)
	}
	return converted, nil
}

func (cs *checkout) convertCurrency(ctx context.Context, from *pb.Money, toCurrency string) (*pb.Money, error) {
	var result *pb.Money
	err := retryRead(ctx, time.Second, 100*time.Millisecond, func(callCtx context.Context) error {
		var callErr error
		result, callErr = cs.currencySvcClient.Convert(callCtx, &pb.CurrencyConversionRequest{
			From:   from,
			ToCode: toCurrency,
		})
		return callErr
	})
	if err != nil {
		return nil, fmt.Errorf("failed to convert currency: %w", err)
	}
	return result, nil
}

func normalizeCurrencyCode(code string) (string, error) {
	code = strings.ToUpper(code)
	if len(code) != 3 {
		return "", fmt.Errorf("user_currency must be a three-letter currency code")
	}
	for _, r := range code {
		if r < 'A' || r > 'Z' {
			return "", fmt.Errorf("user_currency must be a three-letter currency code")
		}
	}
	return code, nil
}

func validateUSDMoney(value *pb.Money) error {
	if err := validateMoneyInCurrency(value, "USD"); err != nil {
		return err
	}
	return nil
}

func validateMoneyInCurrency(value *pb.Money, currency string) error {
	if value == nil || value.GetCurrencyCode() == "" || !money.IsValid(value) {
		return fmt.Errorf("invalid money value")
	}
	if value.GetCurrencyCode() != currency {
		return fmt.Errorf("unexpected currency %q", value.GetCurrencyCode())
	}
	return nil
}

func copyMoney(value *pb.Money) *pb.Money {
	return &pb.Money{CurrencyCode: value.GetCurrencyCode(), Units: value.GetUnits(), Nanos: value.GetNanos()}
}

func multiplyMoney(value *pb.Money, quantity int32) (*pb.Money, error) {
	if quantity < 0 || !money.IsValid(value) || value.GetCurrencyCode() == "" {
		return nil, fmt.Errorf("invalid money multiplication: quantity=%d value=%v", quantity, value)
	}
	units := value.GetUnits() * int64(quantity)
	nanos := int64(value.GetNanos()) * int64(quantity)
	units += nanos / 1_000_000_000
	nanos %= 1_000_000_000
	if (units > 0 && nanos < 0) || (units < 0 && nanos > 0) {
		if units > 0 {
			units--
			nanos += 1_000_000_000
		} else {
			units++
			nanos -= 1_000_000_000
		}
	}
	out := &pb.Money{CurrencyCode: value.GetCurrencyCode(), Units: units, Nanos: int32(nanos)}
	if !money.IsValid(out) {
		return nil, fmt.Errorf("invalid money multiplication result")
	}
	return out, nil
}

func checkoutStatusError(err error) error {
	switch status.Code(err) {
	case codes.InvalidArgument, codes.NotFound, codes.Unavailable, codes.DeadlineExceeded:
		return status.Error(status.Code(err), err.Error())
	}
	if errors.Is(err, context.Canceled) || errors.Is(err, context.DeadlineExceeded) {
		return status.Error(codes.DeadlineExceeded, err.Error())
	}
	return status.Error(codes.Internal, err.Error())
}

func (cs *checkout) chargeCard(ctx context.Context, amount *pb.Money, paymentInfo *pb.CreditCardInfo) (string, error) {
	paymentService := cs.paymentSvcClient
	if cs.isFeatureFlagEnabled(ctx, "paymentUnreachable") {
		badAddress := "badAddress:50051"
		c := mustCreateClient(badAddress)
		paymentService = pb.NewPaymentServiceClient(c)
	}

	callCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	paymentResp, err := paymentService.Charge(callCtx, &pb.ChargeRequest{
		Amount:     amount,
		CreditCard: paymentInfo})
	if err != nil {
		return "", fmt.Errorf("could not charge the card: %+v", err)
	}
	return paymentResp.GetTransactionId(), nil
}

func (cs *checkout) sendOrderConfirmation(ctx context.Context, email string, order *pb.OrderResult) error {
	emailPayload, err := json.Marshal(map[string]interface{}{
		"email": email,
		"order": order,
	})
	if err != nil {
		return fmt.Errorf("failed to marshal order to JSON: %+v", err)
	}

	callCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()

	resp, err := otelhttp.Post(callCtx, cs.emailSvcAddr+"/send_order_confirmation", "application/json", bytes.NewBuffer(emailPayload))
	if err != nil {
		return fmt.Errorf("failed POST to email service: %+v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("failed POST to email service: expected 200, got %d", resp.StatusCode)
	}

	return err
}

func (cs *checkout) shipOrder(ctx context.Context, address *pb.Address, items []*pb.CartItem) (string, error) {
	shipPayload, err := json.Marshal(map[string]interface{}{
		"address": address,
		"items":   items,
	})
	if err != nil {
		return "", fmt.Errorf("failed to marshal ship order request: %+v", err)
	}

	callCtx, cancel := context.WithTimeout(ctx, 3*time.Second)
	defer cancel()

	resp, err := otelhttp.Post(callCtx, cs.shippingSvcAddr+"/ship-order", "application/json", bytes.NewBuffer(shipPayload))
	if err != nil {
		return "", fmt.Errorf("failed POST to shipping service: %+v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("failed POST to shipping service: expected 200, got %d", resp.StatusCode)
	}

	trackingRespBytes, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("failed to read ship order response: %+v", err)
	}

	var shipResp struct {
		TrackingID string `json:"tracking_id"`
	}
	if err := json.Unmarshal(trackingRespBytes, &shipResp); err != nil {
		return "", fmt.Errorf("failed to unmarshal ship order response: %+v", err)
	}
	if shipResp.TrackingID == "" {
		return "", fmt.Errorf("ship order response missing tracking_id field")
	}

	return shipResp.TrackingID, nil
}

func (cs *checkout) sendToPostProcessor(ctx context.Context, result *pb.OrderResult) {
	producer := cs.getKafkaProducer()
	if producer == nil {
		logger.Warn("Kafka producer not connected yet (still retrying) - skipping post-processor notification for this order")
		return
	}

	message, err := proto.Marshal(result)
	if err != nil {
		logger.Error(fmt.Sprintf("Failed to marshal message to protobuf: %+v", err))
		return
	}

	msg := sarama.ProducerMessage{
		Topic: kafka.Topic,
		Value: sarama.ByteEncoder(message),
	}

	// Inject tracing info into message
	span := createProducerSpan(ctx, &msg)
	defer span.End()

	// Send message and handle response
	startTime := time.Now()
	select {
	case producer.Input() <- &msg:
		select {
		case successMsg := <-producer.Successes():
			span.SetAttributes(
				attribute.Bool("messaging.kafka.producer.success", true),
				attribute.Int("messaging.kafka.producer.duration_ms", int(time.Since(startTime).Milliseconds())),
				attribute.KeyValue(semconv.MessagingKafkaMessageOffset(int(successMsg.Offset))),
			)
			logger.Info(fmt.Sprintf("Successful to write message. offset: %v, duration: %v", successMsg.Offset, time.Since(startTime)))
		case errMsg := <-producer.Errors():
			span.SetAttributes(
				attribute.Bool("messaging.kafka.producer.success", false),
				attribute.Int("messaging.kafka.producer.duration_ms", int(time.Since(startTime).Milliseconds())),
			)
			span.SetStatus(otelcodes.Error, errMsg.Err.Error())
			logger.Error(fmt.Sprintf("Failed to write message: %v", errMsg.Err))
		case <-ctx.Done():
			span.SetAttributes(
				attribute.Bool("messaging.kafka.producer.success", false),
				attribute.Int("messaging.kafka.producer.duration_ms", int(time.Since(startTime).Milliseconds())),
			)
			span.SetStatus(otelcodes.Error, "Context cancelled: "+ctx.Err().Error())
			logger.Warn(fmt.Sprintf("Context canceled before success message received: %v", ctx.Err()))
		}
	case <-ctx.Done():
		span.SetAttributes(
			attribute.Bool("messaging.kafka.producer.success", false),
			attribute.Int("messaging.kafka.producer.duration_ms", int(time.Since(startTime).Milliseconds())),
		)
		span.SetStatus(otelcodes.Error, "Failed to send: "+ctx.Err().Error())
		logger.Error(fmt.Sprintf("Failed to send message to Kafka within context deadline: %v", ctx.Err()))
		return
	}

	ffValue := cs.getIntFeatureFlag(ctx, "kafkaQueueProblems")
	if ffValue > 0 {
		logger.Info("Warning: FeatureFlag 'kafkaQueueProblems' is activated, overloading queue now.")
		for i := 0; i < ffValue; i++ {
			go func(i int) {
				producer.Input() <- &msg
				_ = <-producer.Successes()
			}(i)
		}
		logger.Info(fmt.Sprintf("Done with #%d messages for overload simulation.", ffValue))
	}
}

func createProducerSpan(ctx context.Context, msg *sarama.ProducerMessage) trace.Span {
	spanContext, span := tracer.Start(
		ctx,
		fmt.Sprintf("%s publish", msg.Topic),
		trace.WithSpanKind(trace.SpanKindProducer),
		trace.WithAttributes(
			semconv.PeerService("kafka"),
			semconv.NetworkTransportTCP,
			semconv.MessagingSystemKafka,
			semconv.MessagingDestinationName(msg.Topic),
			semconv.MessagingOperationPublish,
			semconv.MessagingKafkaDestinationPartition(int(msg.Partition)),
		),
	)

	carrier := propagation.MapCarrier{}
	propagator := otel.GetTextMapPropagator()
	propagator.Inject(spanContext, carrier)

	for key, value := range carrier {
		msg.Headers = append(msg.Headers, sarama.RecordHeader{Key: []byte(key), Value: []byte(value)})
	}

	return span
}

func (cs *checkout) isFeatureFlagEnabled(ctx context.Context, featureFlagName string) bool {
	client := openfeature.NewClient("checkout")

	// Default value is set to false, but you could also make this a parameter.
	featureEnabled, _ := client.BooleanValue(
		ctx,
		featureFlagName,
		false,
		openfeature.EvaluationContext{},
	)

	return featureEnabled
}

func (cs *checkout) getIntFeatureFlag(ctx context.Context, featureFlagName string) int {
	client := openfeature.NewClient("checkout")

	// Default value is set to 0, but you could also make this a parameter.
	featureFlagValue, _ := client.IntValue(
		ctx,
		featureFlagName,
		0,
		openfeature.EvaluationContext{},
	)

	return int(featureFlagValue)
}
