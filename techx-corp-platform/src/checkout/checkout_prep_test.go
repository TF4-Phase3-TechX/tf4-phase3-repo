package main

import (
	"context"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"go.opentelemetry.io/otel"
	"google.golang.org/grpc"
	"google.golang.org/grpc/codes"
	"google.golang.org/grpc/status"

	pb "github.com/open-telemetry/techx-corp/src/checkout/genproto/oteldemo"
)

type productClient struct {
	get func(context.Context, string) (*pb.Product, error)
}

func (c productClient) ListProducts(context.Context, *pb.Empty, ...grpc.CallOption) (*pb.ListProductsResponse, error) {
	return nil, status.Error(codes.Unimplemented, "unused")
}
func (c productClient) GetProduct(ctx context.Context, req *pb.GetProductRequest, _ ...grpc.CallOption) (*pb.Product, error) {
	return c.get(ctx, req.GetId())
}
func (c productClient) SearchProducts(context.Context, *pb.SearchProductsRequest, ...grpc.CallOption) (*pb.SearchProductsResponse, error) {
	return nil, status.Error(codes.Unimplemented, "unused")
}

type cartClient struct {
	items      []*pb.CartItem
	getErr     error
	emptyCalls atomic.Int32
}

func (c *cartClient) AddItem(context.Context, *pb.AddItemRequest, ...grpc.CallOption) (*pb.Empty, error) {
	return nil, status.Error(codes.Unimplemented, "unused")
}
func (c *cartClient) GetCart(context.Context, *pb.GetCartRequest, ...grpc.CallOption) (*pb.Cart, error) {
	if c.getErr != nil {
		return nil, c.getErr
	}
	return &pb.Cart{Items: c.items}, nil
}
func (c *cartClient) EmptyCart(context.Context, *pb.EmptyCartRequest, ...grpc.CallOption) (*pb.Empty, error) {
	c.emptyCalls.Add(1)
	return &pb.Empty{}, nil
}

type paymentClient struct {
	calls  atomic.Int32
	amount atomic.Pointer[pb.Money]
}

func (c *paymentClient) Charge(_ context.Context, req *pb.ChargeRequest, _ ...grpc.CallOption) (*pb.ChargeResponse, error) {
	c.calls.Add(1)
	c.amount.Store(copyMoney(req.GetAmount()))
	return &pb.ChargeResponse{TransactionId: "tx"}, nil
}

type currencyClient struct {
	convert func(context.Context, *pb.CurrencyConversionRequest) (*pb.Money, error)
	batch   func(context.Context, *pb.BatchCurrencyConversionRequest) (*pb.BatchCurrencyConversionResponse, error)
}

func (c currencyClient) GetSupportedCurrencies(context.Context, *pb.Empty, ...grpc.CallOption) (*pb.GetSupportedCurrenciesResponse, error) {
	return nil, status.Error(codes.Unimplemented, "unused")
}
func (c currencyClient) Convert(ctx context.Context, req *pb.CurrencyConversionRequest, _ ...grpc.CallOption) (*pb.Money, error) {
	return c.convert(ctx, req)
}
func (c currencyClient) BatchConvert(ctx context.Context, req *pb.BatchCurrencyConversionRequest, _ ...grpc.CallOption) (*pb.BatchCurrencyConversionResponse, error) {
	return c.batch(ctx, req)
}

func usd(units int64, nanos int32) *pb.Money {
	return &pb.Money{CurrencyCode: "USD", Units: units, Nanos: nanos}
}
func cartItems(ids ...string) []*pb.CartItem {
	items := make([]*pb.CartItem, len(ids))
	for i, id := range ids {
		items[i] = &pb.CartItem{ProductId: id, Quantity: 1}
	}
	return items
}

func TestNormalizeCurrencyCode(t *testing.T) {
	got, err := normalizeCurrencyCode("eur")
	if err != nil || got != "EUR" {
		t.Fatalf("got %q, %v; want EUR, nil", got, err)
	}
	for _, input := range []string{"", "EU", "EURO", "E1R"} {
		if _, err := normalizeCurrencyCode(input); err == nil {
			t.Fatalf("%q was accepted", input)
		}
	}
}

func TestPrepOrderItemsPreservesOrderAndUsesOneBatch(t *testing.T) {
	var mu sync.Mutex
	var batchCalls, scalarCalls int
	var received []*pb.Money
	cs := &checkout{
		productCatalogSvcClient: productClient{get: func(ctx context.Context, id string) (*pb.Product, error) {
			if id == "first" {
				time.Sleep(20 * time.Millisecond)
			}
			return &pb.Product{
				Id:         id,
				Name:       id + " name",
				Picture:    id + " picture",
				Categories: []string{id + " category"},
				PriceUsd:   usd(map[string]int64{"first": 1, "second": 2, "third": 3}[id], 0),
			}, nil
		}},
		currencySvcClient: currencyClient{
			convert: func(context.Context, *pb.CurrencyConversionRequest) (*pb.Money, error) {
				mu.Lock()
				scalarCalls++
				mu.Unlock()
				return nil, fmt.Errorf("unexpected scalar conversion")
			},
			batch: func(_ context.Context, req *pb.BatchCurrencyConversionRequest) (*pb.BatchCurrencyConversionResponse, error) {
				mu.Lock()
				batchCalls++
				received = append([]*pb.Money(nil), req.GetFrom()...)
				mu.Unlock()
				return &pb.BatchCurrencyConversionResponse{Converted: []*pb.Money{
					{CurrencyCode: "EUR", Units: 10}, {CurrencyCode: "EUR", Units: 20}, {CurrencyCode: "EUR", Units: 30},
				}}, nil
			},
		},
	}

	items := cartItems("first", "second", "third")
	got, err := cs.prepOrderItems(context.Background(), items, "EUR")
	if err != nil {
		t.Fatal(err)
	}
	if batchCalls != 1 || scalarCalls != 0 {
		t.Fatalf("batch=%d scalar=%d, want batch=1 scalar=0", batchCalls, scalarCalls)
	}
	for i, want := range []int64{1, 2, 3} {
		if received[i].GetUnits() != want || got[i].GetItem() != items[i] || got[i].GetCost().GetUnits() != (want*10) {
			t.Fatalf("index %d was not preserved: batch=%v item=%v cost=%v", i, received[i], got[i].GetItem(), got[i].GetCost())
		}
		if display := got[i].GetProductDisplay(); display.GetName() != items[i].GetProductId()+" name" || display.GetPicture() != items[i].GetProductId()+" picture" || len(display.GetCategories()) != 1 || display.GetCategories()[0] != items[i].GetProductId()+" category" {
			t.Fatalf("index %d display=%v", i, display)
		}
	}
}

func TestPrepOrderItemsUSDUsesNoCurrencyRPCs(t *testing.T) {
	var convertCalls, batchCalls int
	cs := &checkout{
		productCatalogSvcClient: productClient{get: func(_ context.Context, id string) (*pb.Product, error) {
			return &pb.Product{
				Id:         id,
				Name:       id + " name",
				Picture:    id + " picture",
				Categories: []string{id + " category"},
				PriceUsd:   usd(map[string]int64{"first": 1, "second": 2}[id], 500000000),
			}, nil
		}},
		currencySvcClient: currencyClient{
			convert: func(context.Context, *pb.CurrencyConversionRequest) (*pb.Money, error) {
				convertCalls++
				return nil, fmt.Errorf("unexpected conversion")
			},
			batch: func(context.Context, *pb.BatchCurrencyConversionRequest) (*pb.BatchCurrencyConversionResponse, error) {
				batchCalls++
				return nil, fmt.Errorf("unexpected batch conversion")
			},
		},
	}

	items := cartItems("first", "second")
	got, err := cs.prepOrderItems(context.Background(), items, "USD")
	if err != nil {
		t.Fatal(err)
	}
	if convertCalls != 0 || batchCalls != 0 {
		t.Fatalf("convert=%d batch=%d, want zero", convertCalls, batchCalls)
	}
	for i, want := range []int64{1, 2} {
		if got[i].GetItem() != items[i] || got[i].GetCost().GetCurrencyCode() != "USD" || got[i].GetCost().GetUnits() != want || got[i].GetCost().GetNanos() != 500000000 || got[i].GetProductDisplay().GetName() != items[i].GetProductId()+" name" {
			t.Fatalf("index %d item=%v cost=%v display=%v", i, got[i].GetItem(), got[i].GetCost(), got[i].GetProductDisplay())
		}
	}
}

func TestPrepOrderItemsFetchesProductsSequentially(t *testing.T) {
	var mu sync.Mutex
	active, maxActive := 0, 0
	cs := &checkout{
		productCatalogSvcClient: productClient{get: func(ctx context.Context, id string) (*pb.Product, error) {
			mu.Lock()
			active++
			if active > maxActive {
				maxActive = active
			}
			mu.Unlock()
			select {
			case <-time.After(15 * time.Millisecond):
			case <-ctx.Done():
				return nil, ctx.Err()
			}
			mu.Lock()
			active--
			mu.Unlock()
			return &pb.Product{Id: id, PriceUsd: usd(1, 0)}, nil
		}},
		currencySvcClient: currencyClient{
			batch: func(_ context.Context, req *pb.BatchCurrencyConversionRequest) (*pb.BatchCurrencyConversionResponse, error) {
				return &pb.BatchCurrencyConversionResponse{Converted: []*pb.Money{{CurrencyCode: "EUR", Units: 1}, {CurrencyCode: "EUR", Units: 1}, {CurrencyCode: "EUR", Units: 1}, {CurrencyCode: "EUR", Units: 1}}}, nil
			},
		},
	}
	if _, err := cs.prepOrderItems(context.Background(), cartItems("a", "b", "c", "d"), "EUR"); err != nil {
		t.Fatal(err)
	}
	if maxActive != 1 {
		t.Fatalf("max product calls = %d, want 1", maxActive)
	}
}

func TestPrepOrderItemsRejectsInvalidBatchOutput(t *testing.T) {
	tests := []struct {
		name      string
		converted []*pb.Money
	}{
		{"cardinality", []*pb.Money{usd(1, 0)}},
		{"wrong target", []*pb.Money{{CurrencyCode: "USD", Units: 1}, {CurrencyCode: "USD", Units: 1}}},
		{"nil money", []*pb.Money{nil, {CurrencyCode: "EUR", Units: 1}}},
		{"invalid nanos", []*pb.Money{{CurrencyCode: "EUR", Units: 1, Nanos: -1}, {CurrencyCode: "EUR", Units: 1}}},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			cs := &checkout{
				productCatalogSvcClient: productClient{get: func(_ context.Context, id string) (*pb.Product, error) {
					return &pb.Product{Id: id, PriceUsd: usd(1, 0)}, nil
				}},
				currencySvcClient: currencyClient{
					convert: func(_ context.Context, req *pb.CurrencyConversionRequest) (*pb.Money, error) {
						return copyMoney(req.GetFrom()), nil
					},
					batch: func(context.Context, *pb.BatchCurrencyConversionRequest) (*pb.BatchCurrencyConversionResponse, error) {
						return &pb.BatchCurrencyConversionResponse{Converted: tt.converted}, nil
					},
				},
			}
			_, err := cs.prepOrderItems(context.Background(), cartItems("a", "b"), "EUR")
			if err == nil {
				t.Fatal("expected invalid batch response to fail")
			}
			if tt.name == "cardinality" && status.Code(err) != codes.Internal {
				t.Fatalf("code=%s err=%v, want Internal", status.Code(err), err)
			}
		})
	}
}

func TestPlaceOrderPreparationFailuresDoNotWrite(t *testing.T) {
	tests := []struct {
		name       string
		productErr error
		batchErr   error
		quoteCode  int
		convertErr error
	}{
		{"product", status.Error(codes.NotFound, "missing"), nil, http.StatusOK, nil},
		{"batch", nil, status.Error(codes.Unavailable, "currency"), http.StatusOK, nil},
		{"quote", nil, nil, http.StatusServiceUnavailable, nil},
		{"shipping conversion", nil, nil, http.StatusOK, status.Error(codes.Unavailable, "currency")},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			logger = slog.New(slog.NewTextHandler(io.Discard, nil))
			tracer = otel.Tracer("checkout-test")
			var shipOrderCalls atomic.Int32
			shipping := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				switch r.URL.Path {
				case "/get-quote":
					w.WriteHeader(tt.quoteCode)
					if tt.quoteCode == http.StatusOK {
						_, _ = w.Write([]byte(`{"cost_usd":{"currency_code":"USD","units":2}}`))
					}
				case "/ship-order":
					shipOrderCalls.Add(1)
					w.WriteHeader(http.StatusOK)
				}
			}))
			defer shipping.Close()

			cart := &cartClient{items: cartItems("a")}
			payment := &paymentClient{}
			cs := &checkout{
				cartSvcClient: cart,
				productCatalogSvcClient: productClient{get: func(_ context.Context, id string) (*pb.Product, error) {
					if tt.productErr != nil {
						return nil, tt.productErr
					}
					return &pb.Product{Id: id, PriceUsd: usd(3, 0)}, nil
				}},
				currencySvcClient: currencyClient{
					convert: func(_ context.Context, req *pb.CurrencyConversionRequest) (*pb.Money, error) {
						if tt.convertErr != nil {
							return nil, tt.convertErr
						}
						return copyMoney(req.GetFrom()), nil
					},
					batch: func(_ context.Context, req *pb.BatchCurrencyConversionRequest) (*pb.BatchCurrencyConversionResponse, error) {
						if tt.batchErr != nil {
							return nil, tt.batchErr
						}
						return &pb.BatchCurrencyConversionResponse{Converted: []*pb.Money{{CurrencyCode: "EUR", Units: 3}}}, nil
					},
				},
				paymentSvcClient: payment,
				shippingSvcAddr:  shipping.URL,
			}
			_, err := cs.PlaceOrder(context.Background(), &pb.PlaceOrderRequest{UserId: "u", UserCurrency: "EUR"})
			if err == nil {
				t.Fatal("expected preparation failure")
			}
			if payment.calls.Load() != 0 || shipOrderCalls.Load() != 0 || cart.emptyCalls.Load() != 0 {
				t.Fatalf("writes occurred: payment=%d ship=%d empty=%d", payment.calls.Load(), shipOrderCalls.Load(), cart.emptyCalls.Load())
			}
		})
	}
}

func TestPlaceOrderKeepsExactMoneyTotal(t *testing.T) {
	logger = slog.New(slog.NewTextHandler(io.Discard, nil))
	tracer = otel.Tracer("checkout-test")
	shipping := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/get-quote":
			_, _ = w.Write([]byte(`{"cost_usd":{"currency_code":"USD","units":1,"nanos":750000000}}`))
		case "/ship-order":
			_, _ = w.Write([]byte(`{"tracking_id":"tracking"}`))
		}
	}))
	defer shipping.Close()

	items := []*pb.CartItem{{ProductId: "a", Quantity: 2}, {ProductId: "b", Quantity: 3}}
	var convertCalls int
	payment := &paymentClient{}
	cs := &checkout{
		cartSvcClient: &cartClient{items: items},
		productCatalogSvcClient: productClient{get: func(_ context.Context, id string) (*pb.Product, error) {
			if id == "a" {
				return &pb.Product{Id: id, PriceUsd: usd(2, 500000000)}, nil
			}
			return &pb.Product{Id: id, PriceUsd: usd(0, 250000000)}, nil
		}},
		currencySvcClient: currencyClient{
			convert: func(_ context.Context, req *pb.CurrencyConversionRequest) (*pb.Money, error) {
				convertCalls++
				return copyMoney(req.GetFrom()), nil
			},
			batch: func(context.Context, *pb.BatchCurrencyConversionRequest) (*pb.BatchCurrencyConversionResponse, error) {
				return nil, fmt.Errorf("unexpected batch")
			},
		},
		paymentSvcClient: payment,
		shippingSvcAddr:  shipping.URL,
	}
	if _, err := cs.PlaceOrder(context.Background(), &pb.PlaceOrderRequest{UserId: "u", UserCurrency: "USD"}); err != nil {
		t.Fatal(err)
	}
	got := payment.amount.Load()
	if got == nil || got.GetCurrencyCode() != "USD" || got.GetUnits() != 7 || got.GetNanos() != 500000000 {
		t.Fatalf("charge=%v, want USD 7.500000000", got)
	}
	if convertCalls != 1 {
		t.Fatalf("convert calls=%d, want 1 shipping conversion", convertCalls)
	}
}
